import argparse
import datetime as dt
import csv
from enum import Enum
from base64 import b64encode
import json
from typing import Literal
import requests
from pprint import pprint

# User-configured settings
# TODO: move out of this file to avoid accidentally commiting secrets
JIRA_EMAIL = None
JIRA_TOKEN = None
PROJECT_KEY = "DW"
JIRA_BASE_URL = "https://joinhonor.atlassian.net"

# REST API constants
SEARCH_API_ENDPOINT = "/rest/api/2/search"
ISSUES_API_ENDPOINT = "/rest/api/2/issue"
BOARD_ENDPOINT = "/rest/agile/1.0/board"


class IssueType(Enum):
    # These values came from the Directed Work project and may
    # differ for different projects.
    INITIATIVE = "Initiative"
    EPIC = "Epic"
    STORY = "Story"
    TASK = "Task"
    BUG = "Bug"
    SUBTASK = "Sub-task"
    ENG_DESIGN = "Eng Design"
    RELEASE = "Release"
    FEATURE_FLAG = "Feature Flag"
    DESIGN = "Design"

    def add_jira_id(self, _id: str):
        self.jira_id = _id


class AuthenticatedRequest:
    """Wrapper around `requests` that adds auth header"""

    def _headers(self):
        auth = f"{JIRA_EMAIL}:{JIRA_TOKEN}"
        return {
            "Authorization": f"Basic {b64encode(auth.encode()).decode()}",
            "Content-Type": "application/json",
        }

    def get(self, url, params=None):
        response = requests.get(url, headers=self._headers(), params=params or {})
        response.raise_for_status()
        return response.json()

    def post(self, url, data):
        response = requests.post(url, headers=self._headers(), data=json.dumps(data))
        response.raise_for_status()
        return response.json()


def get_issue_types(project_key):
    # TODO: construct enum dynamically
    data = get_create_metadata(project_key)
    for issue_type in data["issuetypes"]:
        try:
            enum_value = IssueType(issue_type["name"])
            enum_value.add_jira_id(issue_type["id"])
        except:
            print(f"{issue_type['name']} is not a known IssueType value")
    return data["issuetypes"]


def get_create_field_metadata(project_key: str, issue_type: IssueType):
    url = f"{JIRA_BASE_URL}/rest/api/3/issue/createmeta/{project_key}/issuetypes/{issue_type.jira_id}"
    data = AuthenticatedRequest().get(url)
    required_fields = [f for f in data["fields"] if f["required"]]
    print(f"Required fields: {[f['key'] for f in required_fields]}")
    return [
        {
            "name": f["name"],
            "key": f["key"],
            "required": f["required"],
            "schemaType": f["schema"]["type"],
            "operations": f["operations"],
        }
        for f in data["fields"]
    ]


def get_create_metadata(project_key: str | None = None):
    url = f"{JIRA_BASE_URL}{ISSUES_API_ENDPOINT}/createmeta"
    data = AuthenticatedRequest().get(url)["projects"]
    if project_key:
        for project in data:
            if project["key"] == project_key:
                return project
        raise ValueError(f"{project_key} not found")
    return data


def get_board_id(
    project_key: str,
    board_type: Literal["scrum"] | Literal["kanban"] = "scrum",
) -> str:
    # https://developer.atlassian.com/cloud/jira/software/rest/api-group-board/#api-rest-agile-1-0-board-get
    url = f"{JIRA_BASE_URL}{BOARD_ENDPOINT}"
    params = {"projectKeyOrId": project_key, "type": board_type}
    data = AuthenticatedRequest().get(url, params=params)
    if len(data["values"]) != 1:
        board_names = ", ".join(
            [str(board["name"], board["id"]) for board in data["values"]]
        )
        raise ValueError(
            f"Found {len(data['values'])} boards: {board_names}. "
            "Try setting the --board_id option directly"
        )
    assert len(data["values"]) == 1
    return data["values"][0]["id"]


def get_current_sprint_id(board_id: str) -> str:
    url = f"{JIRA_BASE_URL}{BOARD_ENDPOINT}/{board_id}/sprint"
    params = {"state": "active"}
    data = AuthenticatedRequest().get(url, params=params)
    if "values" in data and len(data["values"]) > 0:
        return data["values"][0]["id"]
    raise ValueError(f"No active sprint found for {project_key}")


def create_issue(
    project_key: str,
    issue_type: IssueType,
    summary: str,
    priority: str | None = None,
    description: str | None = None,
    parent_key: str | None = None,
    epic_key: str | None = None,
    sprint_id: str | None = None,
) -> str:
    """Creates an issue and returns a link to it"""
    data = {
        "project": {"key": project_key},
        "issuetype": {"name": issue_type.value},
        "summary": summary,
    }
    if priority:
        # This option has not been tested...
        data["priority"] = {"name": priority}
    if description:
        data["description"] = description
    if parent_key:
        # This option has not been tested...
        data["customfield_10009"] = parent_key
    if epic_key:
        data["customfield_10008"] = epic_key
    if sprint_id:
        data["customfield_10010"] = sprint_id

    url = f"{JIRA_BASE_URL}{ISSUES_API_ENDPOINT}"
    data = AuthenticatedRequest().post(url, data={"fields": data})
    return f"{JIRA_BASE_URL}/browse/{data['key']}"


def get_issue(key: str):
    issues = get_issues(assignee=None, project=None, keys=[key])
    assert len(issues) == 1
    return issues[0]


def get_issues(
    assignee: str | None = "currentuser()",
    project: str | None = None,
    in_current_sprint=False,
    statuses=None,
    keys=None,
):
    jql_parts = []
    if assignee:
        jql_parts.append(f"assignee={assignee}")
    if project:
        jql_parts.append(f"project = {project}")
    if in_current_sprint:
        jql_parts.append("sprint IN openSprints()")
    if statuses:
        status_list = ", ".join([status.value for status in statuses])
        jql_parts.append(f"status IN ({status_list})")
    if keys:
        if len(keys) == 1:
            jql_parts.append(f'issueKey = "{keys[0]}"')
        else:
            keys_list = ", ".join([f'"{k}"' for k in keys])
            jql_parts.append(f"issueKey IN ({keys_list})")

    params = {
        "jql": " AND ".join(jql_parts),
        #'fields': 'summary,description'
    }

    url = f"{JIRA_BASE_URL}{SEARCH_API_ENDPOINT}"
    data = AuthenticatedRequest().get(url, params=params)
    return sorted(
        data["issues"], key=lambda issue: dt.datetime.fromisoformat(issue["updated"])
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "filename", help="CSV file containing bugs to create issues for"
    )
    parser.add_argument("--epic", help="Optional epic to set as parent")
    parser.add_argument(
        "--board_id",
        help=(
            "Numeric id of the sprint board in Jira. Only necessary if adding "
            "to current sprint and the project has more than one board"
        ),
    )
    priority_values = [
        "Stop ship",
        "Ship before complete",
        "Design input needed",
        "Nice to have",
    ]
    parser.add_argument(
        "--priority",
        help=(
            f"Priority to create tickets for. Expected values: {priority_values}. "
            "Default: Stop ship"
        ),
        default="Stop ship",
    )
    parser.add_argument(
        "--list_fields",
        help="List all possible fields for a bug in this project and exit",
        action="store_true",
    )
    parser.add_argument(
        "--add_to_sprint",
        help="Optionally add bugs to the current sprint upon creation",
        action="store_true",
    )
    args = parser.parse_args()

    if not PROJECT_KEY or not JIRA_TOKEN:
        print("Set your API token and project in `Config`")
    project_key = PROJECT_KEY

    # Example issue data to help with fields for a new issue
    # pprint(get_issue('DW-216'))

    # Validate our enum of issue types + stash the jira ID on the enum values
    get_issue_types(project_key)

    if args.list_fields:
        # List all fields that can be set at issue creation time. Fields
        # may differ by project, so this can be useful to learn about the
        # custom field keys.
        data = get_create_field_metadata(project_key, IssueType.BUG)
        pprint(data)
        exit()

    if args.add_to_sprint:
        print("Getting current sprint...")
        if not args.board_id:
            args.board_id = get_board_id(project_key)
        sprint_id = get_current_sprint_id(str(args.board_id))
    else:
        sprint_id = None

    print(f"Reading CSV {args.filename}")

    matching_rows = []
    with open(args.filename, "r", newline="") as f:
        # Validate columns
        expected_cols = [
            "Priority",
            "Description of issue",
            "Additional notes",
            "Platform/URL",
            "Title",
        ]
        temp_reader = csv.reader(f)
        cols = [c for c in next(temp_reader) if c]
        if len(set(cols)) != len(cols):
            raise ValueError("One or more columns in csv is repeated")
        missing_cols = set(expected_cols) - set(cols)
        if missing_cols:
            raise ValueError(f"Expected columns are missing from csv: {missing_cols}")

        # Reset and read csv
        f.seek(0)
        reader = csv.DictReader(f)

        for row in reader:
            priority = row["Priority"]
            if priority == args.priority:
                matching_rows.append(row)

    print(
        f"Found {len(matching_rows)} bugs with priority {args.priority}. "
        "Creating tickets..."
    )
    for row in matching_rows:
        description = row["Description of issue"]
        title = row["Title"] or description
        notes = row["Additional notes"]
        if notes:
            description += f"\n\n**Additional notes**:\n{notes}"
        url = row["Platform/URL"]
        if url:
            description += f"\n\n**Platform/URL**: {url}"

        kwargs = {
            "project_key": project_key,
            "issue_type": IssueType.BUG,
            "summary": title,
            "description": description,
            "epic_key": args.epic,
            "sprint_id": sprint_id,
        }

        print("\nCreate a bug with the following data?")
        pprint(kwargs, sort_dicts=False, indent=2)
        should_create = input("Y/n > ")
        if should_create.strip().lower() in ("y", ""):
            issue_url = create_issue(**kwargs)
            print(issue_url)
        else:
            print("Skipping.")
