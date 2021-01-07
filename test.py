from urllib.parse import urlparse

moderators = ["itstheredditpolice", "itstheredditbot"]

user = "!strike u/itstheredditpolice notygood reddit.com"


if user[:7] == "!strike":
    print("true")

else:
    print("no")

print(user[:8])