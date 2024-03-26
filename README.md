# One-file script to create Jira tickets from a CSV

## Setup
Install dependencies:
```
pip install requests
```

## Running
A CSV must exist with the following columns (any order):
1. **Priority**: used to decide if we create an issue from this row. By default, only
   a value of "Stop ship" will be attended to.
1. **Description of issue**: will become the Jira ticket description. Also used for the
   title if no title is given.
1. **Additional notes**: will be added to the description if present
1. **Platform/URL**: will be added to the description if present
1. **Title**: used for the Jira ticket summary

The most basic version will create issues in Jira for rows with Priority of "Stop
ship". These issues will not be nested under a parent or epic, and will not be part
of a sprint.
```
python create_bug_tickets.py input.csv
```

Or, to add to the current sprint and set the epic:
```
python create_bug_tickets.py input.csv --add_to_sprint --epic DW-67
```
