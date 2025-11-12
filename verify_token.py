import requests
import xml.etree.ElementTree as ET

# --- CONFIGURATION: FILL IN YOUR DETAILS HERE ---
TABLEAU_SERVER_URL = "https://prod-apsoutheast-a.online.tableau.com"
TABLEAU_SITE_NAME = "sphmedia"
TABLEAU_PAT_NAME = "Your_PAT_Name_Here"
TABLEAU_PAT_SECRET = "Your_PAT_Secret_Here"
# ---------------------------------------------------

API_VERSION = "3.22"

def verify_token():
    """A simple script to verify Tableau PAT credentials."""
    print("--- Verifying Tableau PAT ---")
    
    signin_payload = {
        "credentials": {
            "personalAccessTokenName": TABLEAU_PAT_NAME,
            "personalAccessTokenSecret": TABLEAU_PAT_SECRET,
            "site": {"contentUrl": TABLEAU_SITE_NAME}
        }
    }
    
    # We must ask for XML to handle the server anomaly
    signin_headers = {'Content-Type': 'application/json', 'Accept': 'application/xml'}
    signin_url = f"{TABLEAU_SERVER_URL}/api/{API_VERSION}/auth/signin"
    
    try:
        response = requests.post(signin_url, json=signin_payload, headers=signin_headers, timeout=20)
        response.raise_for_status() # Fail on HTTP error codes

        # Check if the response is valid XML and contains a token
        ET.fromstring(response.content).find('.//{http://tableau.com/api}credentials').get('token')
        
        print("\nSUCCESS! Your PAT Name and Secret are valid.")
        
        # Sign out to be clean
        auth_token = ET.fromstring(response.content).find('.//{http://tableau.com/api}credentials').get('token')
        headers = {"X-Tableau-Auth": auth_token}
        signout_url = f"{TABLEAU_SERVER_URL}/api/{API_VERSION}/auth/signout"
        requests.post(signout_url, headers=headers, timeout=10)

    except requests.exceptions.RequestException as e:
        print("\nFAILED. There was a problem authenticating.")
        if e.response is not None:
            print(f"   Status Code: {e.response.status_code}")
            print(f"   Response: {e.response.text[:300]}") # Show first 300 chars of response
        else:
            print(f"   Error: {e}")

if __name__ == "__main__":
    verify_token()
