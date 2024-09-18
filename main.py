import configparser
from collections import Counter
import json
import logging
import sys

from asyncio.exceptions import TimeoutError
from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.exceptions import TransportServerError, TransportQueryError
from graphql.error.graphql_error import GraphQLError
import requests


log_handler = logging.StreamHandler(sys.stdout)
log_handler.setLevel(logging.DEBUG)
my_format = logging.Formatter("%(levelname)s %(asctime)s %(message)s")
log_handler.setFormatter(my_format)

logger = logging.getLogger(__name__)
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)


# Format for our final JSON output
output = {"domains": [], "computers": {"operatingSystems": {}}}

# Load the config file values
config = configparser.ConfigParser()
config.read("config.ini")

# BloodHound and Ghostwriter API URLs and variables
BH_API_URL = f"{config['bloodhound']['bh_url'].strip('/')}/api/v2/"
GHOSTWRITER_API_URL = f"{config['ghostwriter']['gw_url'].strip('/')}/v1/graphql"
GW_REPORT_ID = config["ghostwriter"]["report_id"]

# Login payload and headers for the BloodHound API
login_payload = {
  "login_method": "secret",
  "username": config["bloodhound"]["username"],
  "secret": config["bloodhound"]["secret"]
}

headers = {
    "Content-Type": "application/json"
}

# Cypher queries for BloodHound

# Return all computers for a given domain
computer_query = 'MATCH (n:Computer) WHERE n.domain = "{domain}" RETURN n'

# Return all users with a password last set date older than 90 days
old_pwd_query = 'MATCH (u:User) WHERE u.pwdlastset < (datetime().epochseconds - (90 * 86400)) and NOT u.pwdlastset IN [-1.0, 0.0] and u.domain = "{domain}" RETURN u'


def run_cypher_query(query, include_properties=False):
    """Execute a Cypher query via the BloodHound API and return the data"""
    r = requests.post(f"{BH_API_URL}graphs/cypher", json={"query": query, "include_properties": include_properties}, headers=headers)
    if r.ok:
        return r.json()["data"]
    if r.status_code == 404:
        logger.info("No data returned for this Cypher query")
        return []
    else:
        logger.warning(f"Failed to run Cypher query: {r.status_code} - {r.text}")
        return []

# Login with username and password and add the resulting token to the headers
res = requests.post(f"{BH_API_URL}login", json=login_payload, headers=headers)

logger.info(f"Logging in to BloodHound API as {config['bloodhound']['username']}")
if res.ok:
    token = res.json()["data"]["session_token"]
    headers["Authorization"] = f"Bearer {token}"
else:
    logger.error(f"Failed to login: {res.status_code} - {res.text}")
    exit(1)

# Get all available domains from the dataset
res = requests.get(f"{BH_API_URL}available-domains", headers=headers)

domains = []
if res.ok:
    domains = res.json()["data"]
else:
    logger.error(f"Failed to get domains: {res.status_code} - {res.text}")
    exit(1)

# Get domain data for each collected domain
for domain in domains:
    domain_output = {}
    domain_data = {}

    logger.info(f"Getting domain data for {domain['name']}")

    res = requests.get(f"{BH_API_URL}domains/{domain['id']}", headers=headers)
    if res.ok:
        domain_data = res.json()["data"]
        props = domain_data["props"]

        domain_output["name"] = props["name"]
        domain_output["domain"] = props["domain"]
        domain_output["distinguishedname"] = props["distinguishedname"]
        domain_output["functionallevel"] = props["functionallevel"]

        domain_output["computers"] = {}
        domain_output["computers"]["count"] = domain_data["computers"]
        domain_output["computers"]["operatingSystems"] = {}

        domain_output["users"] = {}
        domain_output["users"]["count"] = domain_data["users"]
        domain_output["users"]["oldPwdLastSet"] = 0

        domain_output["inboundTrusts"] = []
        domain_output["outboundTrusts"] = []
    else:
        logger.warning(f"Failed to get domain data for {domain['name']}: {res.status_code} - {res.text}")
        continue

    # Get all inbound and outbound trusts for the domain
    if "inboundTrusts" in domain_data:
        if domain_data["inboundTrusts"] > 0:
            res = requests.get(f"{BH_API_URL}domains/{domain['id']}/inbound-trusts", headers=headers)
            for trust in res.json()["data"]:
                domain_output["inboundTrusts"].append(trust["name"])

    if "outboundTrusts" in domain_data:
        if domain_data["outboundTrusts"] > 0:
            res = requests.get(f"{BH_API_URL}domains/{domain['id']}/outbound-trusts", headers=headers)
            for trust in res.json()["data"]:
                domain_output["outboundTrusts"].append(trust["name"])

    # Get all computers in the domain and calculate some statistics
    domain_computers = run_cypher_query(computer_query.format(domain=domain["name"]), True)
    operating_systems = [
        values["properties"]["operatingsystem"]
        for computer, values in domain_computers["nodes"].items()
        if "properties" in values and "operatingsystem" in values["properties"]
    ]

    # Count the occurrences of each operating system
    os_counter = Counter(operating_systems)
    domain_output["computers"]["operatingSystems"] = os_counter

    # Get all users within the domain with a password last set date older than 90 days
    domain_users = run_cypher_query(old_pwd_query.format(domain=domain["name"]), True)
    domain_output["users"]["oldPwdLastSet"] = len(domain_users["nodes"])

    # Add the domain data to the final output
    if domain_output:
        output["domains"].append(domain_output)

# Tally up all operating systems across all domains for the final output
all_operating_systems = [
    domain["computers"]["operatingSystems"]
    for domain in output["domains"]
]
# Combine all counters into a single counter
total_os_counter = Counter()
for os_counter in all_operating_systems:
    total_os_counter.update(os_counter)

output["computers"]["operatingSystems"] = total_os_counter

# Write the final JSON to a local file
with open("output.json", "w") as f:
    f.write(json.dumps(output, indent=4))

# Prepare our GraphQL queries
# Query to verify the token and get the current user's information
whoami_query = gql(
    """
    query Whoami {
        whoami {
            username role expires
        }
    }
    """
)

# Query to fetch the report's `extraFields`
fetch_report_query = gql(
    """
    query FetchReport (
        $reportId: bigint!
    ) {
      report_by_pk(id: $reportId) {
        extraFields
      }
    }
    """
)

# Mutation to update the report's `extraFields`
update_extra_fields_mutation = gql(
    """
    mutation UpdateReport (
        $reportId: bigint!,
        $extraFieldsContent: jsonb!
    ) {
      update_report_by_pk(pk_columns: {id: $reportId}, _set: {extraFields: $extraFieldsContent}) {
        extraFields
      }
    }
    """
)

try:
    logger.info("Authenticating to the Ghostwriter API")
    # Prepare an authenticated client for the Ghostwriter API
    gw_headers = {"Authorization": f"Bearer {config['ghostwriter']['api_token']}"}
    transport = AIOHTTPTransport(url=GHOSTWRITER_API_URL, headers=gw_headers)
    authenticated_client = Client(transport=transport, fetch_schema_from_transport=True)

    # Test the token with a `whois` query
    result = authenticated_client.execute(whoami_query)
    logger.info(f"Authenticated as {result['whoami']['username']}")

    # Fetch the current report's `extraFields` and stash the values
    logger.info(f"Fetching field data from report {GW_REPORT_ID}")
    bhce_field = config["ghostwriter"]["bhce_field_name"]
    report_variables = {
        "reportId": GW_REPORT_ID,
    }
    report_result = authenticated_client.execute(fetch_report_query, variable_values=report_variables)
    curr_extra_fields = report_result["report_by_pk"]["extraFields"]

    # Update the report's `extraFields` with the new data
    logger.info(f"Updating field the `{bhce_field}` field with new data")
    curr_extra_fields[bhce_field] = output
    update_variables = {
        "reportId": GW_REPORT_ID,
        "extraFieldsContent": curr_extra_fields,
    }
    update_result = authenticated_client.execute(update_extra_fields_mutation, variable_values=update_variables)
except TimeoutError as e:
    logger.error(f"GraphQL transport query timed out: {e}")
except TransportQueryError as e:
    logger.error(f"GraphQL transport query error: {e}")
except GraphQLError as e:
    logger.error(f"GraphQL error: {e}")
except TransportServerError as e:
    logger.error(f"GraphQL transport server error: {e}")
