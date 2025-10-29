import tableauserverclient as TSC
import sys

def connect_to_site(server_url, site_name, token_name, token_value):
    """
    Authenticates and connects to a specific Tableau site using a PAT.
    Returns a server object.
    'site_name' MUST be the Content URL (Site ID), not the friendly name.
    """
    print(f"Attempting to connect to site '{site_name}' at {server_url}...")
    try:
        tableau_auth = TSC.PersonalAccessTokenAuth(token_name, token_value, site_name)
        server = TSC.Server(server_url, use_server_version=True)
        server.auth.sign_in(tableau_auth)
        
        # We will NOT access any server attributes here (like server.site_id)
        print(f"Successfully signed in to site '{site_name}'.") 
        return server
        
    except Exception as e:
        print(f"FATAL ERROR connecting to site '{site_name}': {e}")
        print("Please check your URL, Site Name (must be Content URL/Site ID), and PAT details.")
        sys.exit(1) # Exit the script if connection fails

# --- New Helper Functions for this Script ---

def get_all_users(server):
    """
    Fetches all users from a server and returns a dictionary
    mapping their username (e.g., email) to their user ID.
    
    Example: {'user@example.com': 'user-id-123', ...}
    """
    print(f"Fetching all users from site '{server.site_id}'...")
    all_users = TSC.Pager(server.users)
    user_map = {user.name: user.id for user in all_users}
    print(f"Found {len(user_map)} users.")
    return user_map

def get_group_name_id_map(server):
    """
    Fetches all groups from a server and returns a dictionary
    mapping the group name to its group ID. Excludes 'All Users'.
    
    Example: {'Sales Group': 'group-id-abc', ...}
    """
    print(f"Fetching all groups from site '{server.site_id}'...")
    all_groups = TSC.Pager(server.groups)
    # Exclude 'All Users' group as it's managed by Tableau
    group_map = {group.name: group.id for group in all_groups if group.name != "All Users"}
    print(f"Found {len(group_map)} groups (excluding 'All Users').")
    return group_map

def get_user_group_names(server, user_id):
    """
    Gets all group names for a specific user ID.
    Excludes 'All Users' group.
    """
    try:
        user_item = server.users.get_by_id(user_id)
        server.users.populate_groups(user_item)
        # Exclude 'All Users' group
        group_names = [group.name for group in user_item.groups if group.name != "All Users"]
        return group_names
    except Exception as e:
        print(f"  -> ERROR: Could not get groups for user ID {user_id}: {e}")
        return []

def add_user_to_group(server, user_id, group_id, user_name, group_name):
    """
    Adds a user to a specific group on the server (works across TSC versions).
    Handles both group_id string and GroupItem object cases safely.
    """
    try:
        # Step 1: Get the group object using its ID
        all_groups = TSC.Pager(server.groups)
        group_item = next((g for g in all_groups if g.id == group_id), None)
        if not group_item:
            print(f"  -> ERROR: Group '{group_name}' (ID: {group_id}) not found on Site B.")
            return
        
        # Step 2: Add the user
        print(f"  -> Adding user '{user_name}' to group '{group_name}' on Site B...")
        server.groups.add_user(group_item, user_id)  # use GroupItem explicitly
        print(f"  -> SUCCESS: Added '{user_name}' to '{group_name}'.")
        
    except TSC.ServerResponseError as e:
        if "is already a member" in str(e):
            print(f"  -> INFO: '{user_name}' already a member of '{group_name}'. Skipping.")
        else:
            print(f"  -> ERROR adding '{user_name}' to '{group_name}': {e}")
    except Exception as e:
        print(f"  -> UNEXPECTED ERROR while adding '{user_name}' to '{group_name}': {e}")



# --- Main Script Execution ---

def main():
    # --- 1. Get Connection Details ---
    
    site_a_url = input("Enter Site A URL (e.g., https://your-tableau-cloud-url): ").strip()
    site_a_name = input("Enter Site A Name (This is the Site ID / Content URL): ").strip()
    site_a_token_name = input("Enter PAT name for Site A: ").strip()
    site_a_token_value = input("Enter PAT value for Site A: ").strip()

    site_b_url = input("Enter Site B URL (e.g., https://your-tableau-cloud-url): ").strip()
    site_b_name = input("Enter Site B Name (This is the Site ID / Content URL): ").strip()
    site_b_token_name = input("Enter PAT name for Site B: ").strip()
    site_b_token_value = input("Enter PAT value for Site B: ").strip()

    server_a = None
    server_b = None

    try:
        # --- 2. Connect to Both Sites ---
        print("\n--- Connecting to Site A (Source) ---")
        server_a = connect_to_site(site_a_url, site_a_name, site_a_token_name, site_a_token_value)
        
        print("\n--- Connecting to Site B (Destination) ---")
        server_b = connect_to_site(site_b_url, site_b_name, site_b_token_name, site_b_token_value)

        # --- 3. Fetch Data ---
        print("\n--- Gathering Data from Servers ---")
        # Get all users from Site A (Source)
        users_in_site_a = get_all_users(server_a) # {'user@a.com': 'id_a1'}
        
        # Get all users from Site B (Destination)
        users_in_site_b = get_all_users(server_b) # {'user@a.com': 'id_b1'}
        
        # Get all groups from Site B (Destination)
        groups_in_site_b = get_group_name_id_map(server_b) # {'Group 1': 'id_g1'}

        print("\n--- Starting User Group Synchronization ---")
        
        # --- 4. Main Synchronization Loop ---
        for user_name, user_id_a in users_in_site_a.items():
            
            if user_name in users_in_site_b:
                user_id_b = users_in_site_b[user_name]
                print(f"\nProcessing user: '{user_name}' (Exists on both sites)")
                
                groups_for_user_in_a = get_user_group_names(server_a, user_id_a)
                
                if not groups_for_user_in_a:
                    print(f"  -> User '{user_name}' is not in any groups on Site A. Nothing to sync.")
                    continue
                
                print(f"  -> Found in Site A groups: {groups_for_user_in_a}")

                for group_name in groups_for_user_in_a:
                    
                    if group_name in groups_in_site_b:
                        group_id_b = groups_in_site_b[group_name]
                        add_user_to_group(server_b, user_id_b, group_id_b, user_name, group_name)
                    else:
                        print(f"  -> WARNING: Group '{group_name}' exists in Site A but not Site B. Skipping.")
            
            else:
                print(f"\nSkipping user: '{user_name}' (Not found in Site B).")

    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
    
    finally:
        # --- 5. Sign Out ---
        if server_a:
            server_a.auth.sign_out()
            print("\nSigned out from Site A.")
        if server_b:
            server_b.auth.sign_out()
            print("Signed out from Site B.")

    print("\n--- Synchronization Script Finished ---")
# Run the main function when the script is executed
if __name__ == "__main__":
    main()
