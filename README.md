# BloodHound X Ghostwriter

This repository contains a proof-of-concept integration between [BloodHound Community Edition](https://github.com/specterops/bloodhound)
and [Ghostwriter](https://github.com/GhostManager/Ghostwriter). The script collects data from a BHCE server, performs some
fundamental analysis, and then sends the data to Ghostwriter for use in reporting.

See this article for more details: [https://posts.specterops.io/ghostwriter-v4-3-976835a7edba](https://posts.specterops.io/ghostwriter-v4-3-976835a7edba)

This POC is not meant to be used as is. It is meant to demonstrate the capabilities of integrating BHCE and Ghostwriter.
This will not work unless your Ghostwriter server is configured to match the example. If you want
to follow along, see below for instructions on setting up your server.

The best use of this POC is to use it as a starting point for your own integration. You can modify the script to fit your
needs or use it as a reference for your own implementation.

## Getting Started

To get started, copy the `config.ini.example` file to `config.yml` and fill-in the required values as you work through
these steps.

You will need a BloodHound Community Edition server and a Ghostwriter v4.3 server. Record the URLs to these servers in
your _config.ini_ file. If you need a server, you can run one or both servers locally in their Docker containers.

**Note:** If you deploy Ghostwriter as a local dev instance (e.g., `./ghostwriter-cli containers up --dev`),
alongside BloodHound, you will need to change BloodHound's default port (8080) to something else, as Ghostwriter also
uses that port for the API when deployed for local development.

### Prepare BloodHound

You will need some data loaded into BloodHound to analyze. The [example data](https://github.com/SpecterOps/BloodHound/wiki/Example-Data)
from BHCE's wiki will work.

The last step for BloodHound is recording your username and password in the _config.ini_ file.

### Prepare Ghostwriter

Next, add an extra field with the JSON type to reports on your Ghostwriter server. The above article used `bhce_data`
for the field name. You can use any name you like, but you will need to update your _config.ini_ file with the correct
field name.

If you want to follow along with the article and use the example _template.docx_, you will also need a rich text field
named `exec_summ` added to your reports. If you name this field something different, you will need to update the template.

Once you have the fields added, create a new report and record the report ID (look in the URL) in your _config.ini_ file.

Then, upload the example _template.docx_ as a new report template. You'll select this report template when generating
a report later.

The last step for Ghostwriter is creating an API token. Create a token under your user profile and record the token in
your _config.ini_ file.

### Prepare the Script

Finally, you will need to install the required Python packages. You can do this by running `pip install -r requirements.txt`.

Once you have the packages installed, you can run the script with `python main.py`. If the servers are configured correctly,
and you have data in BloodHound, you should see the script run successfully and update your JSON field under your report
in Ghostwriter.

The output will look something like this:

```bash
INFO 2024-09-18 16:24:39,858 Logging in to BloodHound API as admin
INFO 2024-09-18 16:24:39,868 Getting domain data for GHOSTWRITER.LOCAL
INFO 2024-09-18 16:24:40,183 Getting domain data for BLOODHOUND.LOCAL
INFO 2024-09-18 16:24:40,516 Getting domain data for SPECTEROPS.LOCAL
INFO 2024-09-18 16:24:40,672 Authenticating to the Ghostwriter API
INFO 2024-09-18 16:24:40,980 Authenticated as admin
INFO 2024-09-18 16:24:40,980 Fetching field data from report 11
INFO 2024-09-18 16:24:41,006 Updating field the `bhce_data` field with new data
```
