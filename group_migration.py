import tableauserverclient as TSC

# Function to authenticate and connect to a Tableau site
def connect_to_site(server_url, site_name, token_name, token_value):
    tableau_auth = TSC.PersonalAccessTokenAuth(token_name, token_value, site_name)
    server = TSC.Server(server_url, use_server_version=True)
    server.auth.sign_in(tableau_auth)
    return server

# Function to fetch all groups from a site, excluding "All Users"
def get_groups(server):
    all_groups = TSC.Pager(server.groups)
    return [group.name for group in all_groups if group.name != "All Users"]

# Function to create groups on another site
def create_groups(server, groups_to_create):
    for group_name in groups_to_create:
        try:
            new_group = TSC.GroupItem(group_name)
            server.groups.create(new_group)
            print(f"Group '{group_name}' created successfully.")
        except Exception as e:
            print(f"Failed to create group '{group_name}': {e}")

# Inputs
site_a_url = input("Enter Site A URL (e.g., https://your-tableau-cloud-url): ").strip()
site_a_name = input("Enter Site A name: ").strip()
site_a_token_name = input("Enter PAT name for Site A: ").strip()
site_a_token_value = input("Enter PAT value for Site A: ").strip()

site_b_url = input("Enter Site B URL (e.g., https://your-tableau-cloud-url): ").strip()
site_b_name = input("Enter Site B name: ").strip()
site_b_token_name = input("Enter PAT name for Site B: ").strip()
site_b_token_value = input("Enter PAT value for Site B: ").strip()

# Connect to Site A and fetch groups
print("\nConnecting to Site A...")
server_a = connect_to_site(site_a_url, site_a_name, site_a_token_name, site_a_token_value)
groups_in_site_a = get_groups(server_a)
server_a.auth.sign_out()

# Display groups with numbering
print("\nGroups in Site A (excluding 'All Users'):")
for i, group in enumerate(groups_in_site_a, 1):
    print(f"{i}. {group}")

# Select groups to exclude by their numbers
exclude_numbers = input("\nEnter the numbers of the groups to exclude (comma-separated): ")
exclude_numbers = [int(num.strip()) for num in exclude_numbers.split(",") if num.strip().isdigit()]

# Filter out the excluded groups
groups_to_import = [group for i, group in enumerate(groups_in_site_a, 1) if i not in exclude_numbers]

# Connect to Site B and create groups
print("\nConnecting to Site B...")
server_b = connect_to_site(site_b_url, site_b_name, site_b_token_name, site_b_token_value)
create_groups(server_b, groups_to_import)
server_b.auth.sign_out()

print("\nDone!")
