#######################
# SCRIPT DOES NOT WORK. WAS JUST USED TO TRY AND TEST SUBSCRIPTION MIGRATION VIA API.
#######################

import tableauserverclient as TSC
import sys
import datetime
import json
import requests
from collections import defaultdict

# --- Connection Details for Site A (Source) ---
SITE_A_URL = 'https://prod-apsoutheast-a.online.tableau.com/'
SITE_A_PAT_NAME = 'pat_name'
SITE_A_PAT_SECRET = 'pat_secret' # <-- UPDATE THIS
SITE_A_CONTENT_URL = 'site_name'

# --- Connection Details for Site B (Destination) ---
SITE_B_URL = 'https://prod-apsoutheast-b.online.tableau.com/'
SITE_B_PAT_NAME = 'pat_name'
SITE_B_PAT_SECRET = 'pat_secret' # <-- UPDATE THIS
SITE_B_CONTENT_URL = 'site_name'


# ======================================================================
#                Helper Functions for Caching
# ======================================================================

def build_user_map(server, by='email'):
    """
    Returns a dictionary mapping user attributes.
    by='email': { 'user@email.com': 'user_id' }
    by='id':    { 'user_id': 'user@email.com' }
    """
    print(f"  Building user map (by {by})...")
    user_map = {}
    for user in TSC.Pager(server.users.get):
        if user.email: # Only map users with emails
            if by == 'email':
                user_map[user.email] = user.id
            elif by == 'id':
                user_map[user.id] = user.email
    print(f"  Found {len(user_map)} users.")
    return user_map

def build_workbook_map_by_name(server):
    """
    Returns a dictionary mapping workbook attributes.
    { 'Workbook Name': 'workbook_id' }
    """
    print(f"  Building workbook map (by name)...")
    wb_map = {}
    for wb in TSC.Pager(server.workbooks.get):
        if wb.name in wb_map:
            print(f"    Warning: Duplicate workbook name found on site '{server.site_id}': {wb.name}. Migration will use the last ID found.")
        wb_map[wb.name] = wb.id
    print(f"  Found {len(wb_map)} workbooks.")
    return wb_map

def build_schedule_maps(server_a, server_b):
    """
    Returns two dictionaries for mapping schedule names across sites.
    1. schedules_a_name_map: { 'schedule_id_A': 'Schedule Name' }
    2. schedules_b_id_map:   { 'Schedule Name': 'schedule_id_B' }
    """
    print("  Building schedule maps...")
    schedules_a_name_map = {}
    for s in TSC.Pager(server_a.schedules.get):
        schedules_a_name_map[s.id] = s.name
    
    schedules_b_id_map = {}
    for s in TSC.Pager(server_b.schedules.get):
        if s.name in schedules_b_id_map:
             print(f"    Warning: Duplicate schedule name found on Site B: {s.name}. Using last ID found.")
        schedules_b_id_map[s.name] = s.id
        
    print(f"  Found {len(schedules_a_name_map)} schedules on Site A and {len(schedules_b_id_map)} on Site B.")
    return schedules_a_name_map, schedules_b_id_map

def get_existing_subscriptions(server_b):
    """
    Returns a set of tuples for existing subscriptions on Site B
    to prevent duplicate creation.
    Format: { (user_id, target_id, schedule_id) }
    """
    print("  Building set of existing subscriptions on Site B...")
    existing_subs = set()
    for sub in TSC.Pager(server_b.subscriptions.get):
        if sub.target and sub.target.id: # Ensure subscription has a target
             existing_subs.add((sub.user_id, sub.target.id, sub.schedule_id))
    print(f"  Found {len(existing_subs)} existing subscriptions.")
    return existing_subs

# ======================================================================
#                       Main Migration Logic
# ======================================================================

# --- 1. Get Workbook Name from User ---
WORKBOOK_NAME_TO_MIGRATE = input("Please enter the exact name of the workbook to migrate subscriptions for: ")
if not WORKBOOK_NAME_TO_MIGRATE:
    print("Error: No workbook name entered. Exiting.")
    sys.exit()

print(f"\nAttempting to migrate subscriptions for workbook: '{WORKBOOK_NAME_TO_MIGRATE}'")

# --- 2. Connect to Servers ---
print("Connecting to Site A (Source)...")
server_a = TSC.Server(SITE_A_URL, use_server_version=True)
auth_a = TSC.PersonalAccessTokenAuth(
    token_name=SITE_A_PAT_NAME,
    personal_access_token=SITE_A_PAT_SECRET,
    site_id=SITE_A_CONTENT_URL
)

print("Connecting to Site B (Destination)...")
server_b = TSC.Server(SITE_B_URL, use_server_version=True)
auth_b = TSC.PersonalAccessTokenAuth(
    token_name=SITE_B_PAT_NAME,
    personal_access_token=SITE_B_PAT_SECRET,
    site_id=SITE_B_CONTENT_URL
)

# Statistics counters
total_subs_checked = 0
total_subs_migrated = 0
total_subs_skipped = 0
total_subs_failed = 0
workbook_a_id = None
workbook_b_id = None

# --- API Details ---
site_id_b = None
auth_token_b = None
api_version_b = None

try:
    with server_a.auth.sign_in(auth_a):
        print(f"Successfully signed in to Site A: {SITE_A_URL}")
        with server_b.auth.sign_in(auth_b):
            print(f"Successfully signed in to Site B: {SITE_B_URL}")
            
            # --- Capture Site B details for API calls ---
            site_id_b = server_b.site_id
            auth_token_b = server_b.auth_token
            api_version_b_detected = server_b.version
            api_version_b = "3.16" # <-- HARD-CODED FOR TESTING
            print(f"  Site B API Version (Detected): {api_version_b_detected}")
            print(f"  Site B API Version (Using): {api_version_b}")
            print(f"  Site B ID: {site_id_b}")
            print(f"  Site B API Version: {api_version_b}")
            
            # --- 3. Build All Caches ---
            print("\nBuilding caches for mapping...")
            users_a_map = build_user_map(server_a, by='id')
            users_b_map = build_user_map(server_b, by='email')
            workbooks_a_map = build_workbook_map_by_name(server_a)
            workbooks_b_map = build_workbook_map_by_name(server_b)
            schedules_a_name_map, schedules_b_id_map = build_schedule_maps(server_a, server_b)
            existing_subs_b = get_existing_subscriptions(server_b)
            print("All caches built.")

            # --- 4. Find Target Workbook IDs ---
            print("\nFinding target workbooks...")
            workbook_a_id = workbooks_a_map.get(WORKBOOK_NAME_TO_MIGRATE)
            workbook_b_id = workbooks_b_map.get(WORKBOOK_NAME_TO_MIGRATE)

            if not workbook_a_id:
                print(f"Error: Workbook '{WORKBOOK_NAME_TO_MIGRATE}' not found on Site A. Exiting.")
                sys.exit()
            if not workbook_b_id:
                print(f"Error: Workbook '{WORKBOOK_NAME_TO_MIGRATE}' not found on Site B. Exiting.")
                sys.exit()
                
            print(f"  Found Workbook on Site A (ID: {workbook_a_id})")
            print(f"  Found Workbook on Site B (ID: {workbook_b_id})")

            # --- 4.5 Build View Maps for Both Sites ---
            print("  Building cache of views for Site A workbook...")
            view_ids_a = set()
            view_a_id_to_name_map = {}
            for view in TSC.Pager(server_a.views.get):
                if view.workbook_id == workbook_a_id:
                    view_ids_a.add(view.id)
                    view_a_id_to_name_map[view.id] = view.name
            print(f"  Found {len(view_ids_a)} views for Site A workbook.")

            print("  Building cache of views for Site B workbook...")
            view_b_name_to_id_map = {}
            for view in TSC.Pager(server_b.views.get):
                 if view.workbook_id == workbook_b_id:
                    view_b_name_to_id_map[view.name] = view.id
            print(f"  Found {len(view_b_name_to_id_map)} views for Site B workbook.")


            # --- 5. Get Subscriptions for the specific workbook ---
            print(f"\nFetching subscriptions for '{WORKBOOK_NAME_TO_MIGRATE}' from Site A...")
            subscriptions_to_migrate = []
            subscription_count = 0

            print("  Paging through all subscriptions on Site A to find matches...")
            for sub in TSC.Pager(server_a.subscriptions.get):
                subscription_count += 1
                if not (sub.target and sub.target.id): continue

                target_id = sub.target.id
                target_type = sub.target.type
                
                if target_type == 'Workbook' and target_id == workbook_a_id:
                    print(f"    Found matching WORKBOOK subscription: {sub.id}")
                    subscriptions_to_migrate.append(sub)
                elif target_type == 'View' and target_id in view_ids_a:
                    print(f"    Found matching VIEW subscription: {sub.id}")
                    subscriptions_to_migrate.append(sub)

            print(f"  (Checked {subscription_count} total subscriptions on Site A)")
            print(f"Found {len(subscriptions_to_migrate)} subscriptions for this workbook.")

            # --- 6. Iterate ONLY those Subscriptions ---
            for sub_a in subscriptions_to_migrate:
                total_subs_checked += 1
                print(f"\n--- Processing Site A Sub ID: {sub_a.id} ---")

                # --- 7. Find Matches in Site B ---
                
                # A. Find User
                user_a_email = users_a_map.get(sub_a.user_id)
                if not user_a_email:
                    print(f"  FAIL: User ID {sub_a.user_id} not found in Site A cache (or has no email).")
                    total_subs_failed += 1
                    continue
                
                user_b_id = users_b_map.get(user_a_email)
                if not user_b_id:
                    print(f"  FAIL: User '{user_a_email}' not found on Site B.")
                    total_subs_failed += 1
                    continue
                # print(f"  User Match: {user_a_email} -> {user_b_id}")

                # B. Find Target (Workbook or View)
                target_id_b = None
                target_type_b = sub_a.target.type
                
                if target_type_b == 'Workbook':
                    target_id_b = workbook_b_id
                    # print("  Target Match: Workbook")
                elif target_type_b == 'View':
                    view_a_name = view_a_id_to_name_map.get(sub_a.target.id)
                    if not view_a_name:
                        print(f"  FAIL: Could not find name for Site A View ID {sub_a.target.id} in cache.")
                        total_subs_failed += 1
                        continue
                    
                    target_id_b = view_b_name_to_id_map.get(view_a_name)
                    if not target_id_b:
                        print(f"  FAIL: Could not find matching view named '{view_a_name}' on Site B workbook.")
                        total_subs_failed += 1
                        continue
                    # print(f"  Target Match: View '{view_a_name}' -> {target_id_b}")
                
                if not target_id_b:
                    print(f"  FAIL: Could not determine target ID on Site B.")
                    total_subs_failed += 1
                    continue

                # C. Find Schedule
                schedule_b_id = None
                schedule_name_for_print = "Custom" # Default for print message
                
                if sub_a.schedule_id:
                    # --- CASE 1: This is a SHARED schedule ---
                    schedule_a_name = schedules_a_name_map.get(sub_a.schedule_id)
                    schedule_name_for_print = schedule_a_name if schedule_a_name else "Unknown Shared"
                    
                    if not schedule_a_name:
                        print(f"  FAIL: Shared Schedule ID {sub_a.schedule_id} not found in Site A cache.")
                        total_subs_failed += 1
                        continue
                    
                    schedule_b_id = schedules_b_id_map.get(schedule_a_name)
                    if not schedule_b_id:
                        print(f"  FAIL: Shared Schedule '{schedule_a_name}' (from Site A) not found on Site B.")
                        total_subs_failed += 1
                        continue
                else:
                    # --- CASE 2: This is a CUSTOM schedule (Tableau Cloud) ---
                    print("  INFO: Custom schedule detected (Schedule ID is None).")
                    
                    schedule_data = sub_a.schedule 
                    custom_schedule_a = None # This is the ScheduleItem object

                    if isinstance(schedule_data, list): 
                        if schedule_data: 
                            custom_schedule_a = schedule_data[0] 
                    elif schedule_data: 
                        custom_schedule_a = schedule_data

                    if not custom_schedule_a:
                        print(f"  FAIL: Subscription {sub_a.id} has a custom schedule but object is empty.")
                        total_subs_failed += 1
                        continue

                    # --- Robust Introspection of Schedule Object ---
                    # This is the key fix. The ScheduleItem may not have .frequency,
                    # but it MUST have .interval_item or .frequency_details.
                    source_schedule_frequency_details_obj = getattr(custom_schedule_a, 'interval_item', None) or getattr(custom_schedule_a, 'frequency_details', None)
                    source_schedule_frequency = None
                    
                    if isinstance(source_schedule_frequency_details_obj, TSC.HourlyInterval): source_schedule_frequency = 'Hourly'
                    elif isinstance(source_schedule_frequency_details_obj, TSC.DailyInterval): source_schedule_frequency = 'Daily'
                    elif isinstance(source_schedule_frequency_details_obj, TSC.WeeklyInterval): source_schedule_frequency = 'Weekly'
                    elif isinstance(source_schedule_frequency_details_obj, TSC.MonthlyInterval): source_schedule_frequency = 'Monthly'
                    else: source_schedule_frequency = getattr(custom_schedule_a, 'frequency', None) # Fallback

                    if not (source_schedule_frequency and source_schedule_frequency_details_obj):
                         print(f"  FAIL: Could not determine frequency and details from custom schedule object for sub {sub_a.id}.")
                         total_subs_failed += 1
                         continue
                    # --- End Robust Introspection ---


                    # --- Construct JSON Payload ---
                    schedule_payload_details = {}
                    intervals_list_for_payload = []
                    # We already defined source_schedule_frequency and source_schedule_frequency_details_obj
                    
                    try:
                        if hasattr(source_schedule_frequency_details_obj, 'start_time') and source_schedule_frequency_details_obj.start_time:
                            schedule_payload_details['start'] = source_schedule_frequency_details_obj.start_time.strftime('%H:%M:%S')
                        else: raise ValueError("Cannot find start_time in custom schedule object.")

                        if hasattr(source_schedule_frequency_details_obj, 'end_time') and source_schedule_frequency_details_obj.end_time:
                             schedule_payload_details['end'] = source_schedule_frequency_details_obj.end_time.strftime('%H:%M:%S')

                        if isinstance(source_schedule_frequency_details_obj, TSC.HourlyInterval):
                            interval_val = getattr(source_schedule_frequency_details_obj, 'interval_value', None)
                            if interval_val == 0.25: intervals_list_for_payload.append({'minutes': 15})
                            elif interval_val == 0.5: intervals_list_for_payload.append({'minutes': 30})
                            elif isinstance(interval_val, int) and interval_val > 0: intervals_list_for_payload.append({'hours': interval_val})
                            else: raise ValueError(f"Invalid hourly interval value: {interval_val}")

                        elif isinstance(source_schedule_frequency_details_obj, TSC.DailyInterval): pass 

                        elif isinstance(source_schedule_frequency_details_obj, TSC.WeeklyInterval):
                            raw_days_obj = getattr(source_schedule_frequency_details_obj, '_interval_expression', None)
                            day_map_rev = {v: k for k, v in TSC.IntervalItem.Day.__dict__.items() if isinstance(v, str) and not k.startswith('_')}
                            if isinstance(raw_days_obj, tuple):
                                for day_const in raw_days_obj:
                                    if day_const in day_map_rev: intervals_list_for_payload.append({'weekday': day_map_rev[day_const]})
                            if not intervals_list_for_payload: # Fallback
                                 raw_days_str = getattr(source_schedule_frequency_details_obj, 'interval_value', None)
                                 if raw_days_str and isinstance(raw_days_str, str):
                                     for day_str in raw_days_str.split(','): intervals_list_for_payload.append({'weekday': day_str.strip()})
                            if not intervals_list_for_payload: raise ValueError("Could not reconstruct days for WeeklyInterval.")

                        elif isinstance(source_schedule_frequency_details_obj, TSC.MonthlyInterval):
                            day_val_int = None; interval_val = getattr(source_schedule_frequency_details_obj, 'interval_value', None)
                            if isinstance(interval_val, int): day_val_int = interval_val
                            elif isinstance(interval_val, str) and interval_val.startswith('Day='):
                                try: day_val_int = int(interval_val.split('=')[1])
                                except: pass
                            if day_val_int is not None: schedule_payload_details['dayOfMonth'] = str(day_val_int)
                            else: raise ValueError("Could not reconstruct MonthlyInterval (day of month). Nth weekday not supported.")

                        if intervals_list_for_payload:
                            schedule_payload_details['intervals'] = intervals_list_for_payload

                    except ValueError as ve:
                        print(f"  FAIL: Error constructing schedule payload: {ve}")
                        total_subs_failed += 1
                        continue
                    
                    # --- Make Direct API Call to Create Schedule ---
                    new_schedule_name = f"Migrated-Sub-{sub_a.id}" # Unique name
                    schedule_name_for_print = new_schedule_name # For the skip message
                    
                    schedule_api_payload = { "schedule": {
                        "name": new_schedule_name, "priority": 50, "type": "Subscription",
                        "frequency": source_schedule_frequency, "frequencyDetails": schedule_payload_details
                    }}
                    
                    api_endpoint = f"{SITE_B_URL.rstrip('/')}/api/{api_version_b}/sites/{site_id_b}/schedules"
                    headers_for_request = { 
                        'X-Tableau-Auth': auth_token_b, 'Content-Type': 'application/json', 'Accept': 'application/json' 
                    }

                    # --- START DEBUGGING ---
                    print(f"\n  DEBUG: API Endpoint: POST {api_endpoint}")
                    print(f"  DEBUG: API Headers: {{'X-Tableau-Auth': '[REDACTED]', 'Content-Type': '{headers_for_request['Content-Type']}', 'Accept': '{headers_for_request['Accept']}'}}")
                    print(f"  DEBUG: API Payload: {json.dumps(schedule_api_payload, indent=2)}")
                    # --- END DEBUGGING ---
                    
                    print(f"  CREATE: Attempting to create new custom schedule '{new_schedule_name}' on Site B via API...")
                    
                    try:
                        response = requests.post(api_endpoint, headers=headers_for_request, data=json.dumps(schedule_api_payload), timeout=30)
                        response.raise_for_status() 
                        response_json = response.json()
                        schedule_b_id = response_json.get('schedule', {}).get('id')
                        
                        if not schedule_b_id:
                            print(f"  FAIL: API call succeeded but did not return a new schedule ID.")
                            total_subs_failed += 1
                            continue
                        print(f"  SUCCESS: Created new schedule (ID: {schedule_b_id})")

                    except requests.exceptions.HTTPError as http_err:
                        print(f"  FAIL: HTTP error creating custom schedule: {http_err}")
                        try: error_details = http_err.response.json(); print(f"  Error Details: {error_details}")
                        except json.JSONDecodeError: print(f"  Response Content: {http_err.response.text}")
                        total_subs_failed += 1
                        continue
                    except Exception as e:
                        print(f"  FAIL: Unexpected error creating schedule: {e}")
                        total_subs_failed += 1
                        continue

                # --- End of Schedule Logic ---
                if not schedule_b_id:
                     print(f"  FAIL: Schedule ID for Site B could not be determined.")
                     total_subs_failed += 1
                     continue

                # --- 8. Check if Subscription Already Exists ---
                subscription_key_b = (user_b_id, target_id_b, schedule_b_id)
                if subscription_key_b in existing_subs_b:
                    print(f"  SKIP: Subscription for '{user_a_email}' on target '{target_id_b}' with schedule '{schedule_name_for_print}' already exists on Site B.")
                    total_subs_skipped += 1
                    continue

                # --- 9. Create Subscription in Site B ---
                print(f"  CREATE: Creating subscription for '{user_a_email}' on target '{target_id_b}' ({target_type_b})...")
                try:
                    new_sub_item = TSC.SubscriptionItem()
                    new_sub_item.target_id = target_id_b   # <-- FIXED
                    new_sub_item.target_type = target_type_b # <-- FIXED
                    new_sub_item.schedule_id = schedule_b_id
                    new_sub_item.user_id = user_b_id
                    
                    # Copy properties
                    new_sub_item.subject = sub_a.subject
                    new_sub_item.message = sub_a.message
                    new_sub_item.attach_image = sub_a.attach_image
                    new_sub_item.attach_pdf = sub_a.attach_pdf
                    
                    server_b.subscriptions.create(new_sub_item)
                    print(f"  SUCCESS: Created new subscription.")
                    total_subs_migrated += 1
                    
                except Exception as e:
                    print(f"  ERROR: Failed to create subscription. {e}")
                    total_subs_failed += 1
            
            print("\nMigration process finished for this workbook.")

except TSC.ServerResponseError as e:
    print(f"\nError: A Tableau Server error occurred.")
    print(e)
    sys.exit(1)
except Exception as e:
    print(f"\nAn unexpected error occurred: {e}")
    sys.exit(1)

# --- 10. Print Summary ---
print("\n--- Migration Summary ---")
print(f"Workbook Processed: {WORKBOOK_NAME_TO_MIGRATE}")
print(f"Total Subscriptions Found on Site A: {total_subs_checked}")
print(f"New Subscriptions Created on Site B: {total_subs_migrated}")
print(f"Subscriptions Skipped (Already Exist): {total_subs_skipped}")
print(f"Subscriptions Failed (Missing User/Schedule/View): {total_subs_failed}")
print("---------------------------\n")

print("Script finished.")
