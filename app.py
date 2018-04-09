import json
import requests
import jinja2
import collections
from urllib.parse import urljoin
from datetime import datetime, timedelta


DATE_FORMAT = "%Y-%m-%d"


TEMPLATE = """
<!DOCTYPE html><html><body>
<table>
    <tr>
        <th> - </th>
        {% for uid in tracking -%}
            <th>{{tracking[uid].name}}</th>
        {% endfor -%}
    </tr>

    {% for pid in projects -%}
        <tr>
            <td>{{projects[pid]}}</td>
            {% for uid in tracking %}
                <td>{{tracking[uid]["projects"][pid]}}</td>
            {% endfor %}
        </tr>
    {% endfor %}
</table>
</body></html>

"""


class Client:
    def __init__(self, cfg_path):
        self.config = json.load(open(cfg_path, "r"))
        self.request_headers = {
            "Auth-Token": self.config["auth_token"],
            "App-Token": self.config["app_token"],
        }

    def mk_api_url(self, endpoint, **kwargs):
        return urljoin(self.config["api_url"], endpoint)

    def get(self, endpoint, **params):
        url = self.mk_api_url(endpoint)
        response = requests.get(
            url,
            data=params,
            headers=self.request_headers,
        )
        print("GET", url, response.status_code)
        if response.status_code in [400]:
            print(response.json())
        assert response.ok
        return response

    def make_report(self, day, output):
        org_id = self.get_organization_id()
        ## Possibly unnecessary (and in such case
        ## getting organization id would probably turn out unnecessary).
        ## I'm unable to check at the moment (no other organizations,
        ## no other time tracked, etc.).
        # members = self.get_organization_members(org_id)
        members = []

        report = self.get_team_report(org_id, day, members)
        html = self.create_output(report)
        with open(output, "w+") as fh:
            fh.write(html)
        print("Wrote:", output)

    def get_organization_members(self, org_id):
        endpoint = "organizations/%d/members" % org_id
        response = self.get(endpoint)
        return response.json().get("users", [])

    def get_team_report(self, org_id, day=None, members=None):
        members = (members or [])
        start_date = None
        end_date = None
        if day:
            start_date = datetime.strptime(day, DATE_FORMAT)
            end_date = start_date + timedelta(1)
        else:
            # yesterday
            start_date = datetime.now() - timedelta(1)
            end_date = datetime.today()

        params = dict(
            start_date=start_date.strftime(DATE_FORMAT),
            end_date=end_date.strftime(DATE_FORMAT),
            organizations=str(org_id),
            users=",".join([str(m["id"]) for m in members]),
            show_tasks=True,
            show_activity=True,
        )
        response = self.get("custom/by_member/team", **params)
        return response.json()

    def get_organization_id(self):
        response = self.get("organizations")
        organizations = response.json() if response.ok else []
        orgs = list(filter(
            lambda org: org["name"] == self.config["organization"],
            organizations["organizations"],
        ))
        assert len(orgs) == 1
        return orgs[0]["id"]

    def create_output(self, data):
        tpl = jinja2.Template(TEMPLATE)

        tracking = collections.OrderedDict()
        all_projects = collections.OrderedDict()

        for org in data["organizations"]:
            for user in org["users"]:
                user_id = user["id"]
                total_duration = sum(
                    map(lambda d: d["duration"], user["dates"])
                )
                if not total_duration: continue
                tracking[user_id] = dict(
                    name=user["name"],
                    id=user_id,
                    projects=dict()
                )
                for date in user["dates"]:
                    for project in date["projects"]:
                        all_projects[project["id"]] = project["name"]
                        projects = tracking[user_id]["projects"]
                        projects[project["id"]] = project["duration"]

        return tpl.render(tracking=tracking, projects=all_projects)

if __name__ == "__main__":
    import argparse


    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config", type=str, default="config.json")
    parser.add_argument(
        "-d", "--date",
        type=str,
        default=datetime.today().strftime(DATE_FORMAT),
        help="date (yyyy-mm-dd)",
    )
    parser.add_argument("-o", "--output", type=str, default="/tmp/output.html")

    args = parser.parse_args()
    cli = Client(args.config)
    cli.make_report(args.date, args.output)
