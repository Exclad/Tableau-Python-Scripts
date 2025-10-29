import requests
import tkinter as tk
from tkinter import messagebox, ttk
import os
import json
from datetime import datetime
import xml.etree.ElementTree as ET

# File to store PAT credentials
CREDENTIALS_FILE = "pat_credentials.json"

# Tableau Cloud Base URL
BASE_URL = "https://prod-apsoutheast-a.online.tableau.com"  # Replace with your specific URL
API_VERSION = "3.24"  # Adjust API version if needed

# Save multiple PAT credentials to a file
def save_credentials(pat_name, pat_secret):
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, "r") as file:
            all_credentials = json.load(file)
    else:
        all_credentials = []

    # Check if the PAT already exists
    if any(cred['pat_name'] == pat_name for cred in all_credentials):
        raise ValueError(f"PAT with name '{pat_name}' already exists.")

    credentials = {"pat_name": pat_name, "pat_secret": pat_secret}
    all_credentials.append(credentials)

    with open(CREDENTIALS_FILE, "w") as file:
        json.dump(all_credentials, file)


# Load PAT credentials from file
def load_credentials():
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, "r") as file:
                credentials = json.load(file)
                # Ensure it's a list
                if isinstance(credentials, list):
                    return credentials
                else:
                    print("Error: Data in credentials file is not a list.")
                    return []
        except json.JSONDecodeError:
            print("Error: Failed to decode JSON. The credentials file might be corrupted.")
            return []
    return []  # Return an empty list if no credentials are found


# Validate PAT and return site name
def validate_pat(pat_name, pat_secret):
    url = f"{BASE_URL}/api/{API_VERSION}/auth/signin"
    headers = {"Content-Type": "application/json"}
    data = {
        "credentials": {
            "personalAccessTokenName": pat_name,
            "personalAccessTokenSecret": pat_secret,
            "site": {"contentUrl": "sphmedia"},  # Replace with your site's content URL
        }
    }

    try:
        # Send POST request
        response = requests.post(url, json=data, headers=headers)
        response.raise_for_status()

        # Parse XML response
        root = ET.fromstring(response.text)

        # Extract site details
        credentials = root.find(".//{http://tableau.com/api}credentials")
        site = credentials.find("{http://tableau.com/api}site")
        site_name = site.attrib.get("contentUrl", "Unknown Site")

        # Fetch additional details (e.g., token expiration)
        time_to_expire = credentials.attrib.get("estimatedTimeToExpiration")

        success_message = f"Connected to site: {site_name}, Token expires in: {time_to_expire}"
        return success_message

    except requests.exceptions.RequestException:
        return "Invalid token. Please check if the token name and secret are correct."

    except ET.ParseError:
        return "Failed to parse XML response."

    except Exception as e:
        return f"Unexpected error: {e}"


# Main UI Application
class TableauUserManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Tableau User Manager")

        # Smaller window size
        self.root.geometry("450x500")
        self.root.resizable(False, False)  # Prevent resizing

        # Load existing PAT credentials
        self.credentials = load_credentials()
        self.auth_token = None

        # Styling for modern look with smaller fonts
        self.style = ttk.Style()
        self.style.configure('TButton', font=('Helvetica', 10), padding=5)
        self.style.configure('TLabel', font=('Helvetica', 10), padding=5)
        self.style.configure('TCombobox', font=('Helvetica', 10), padding=5)

        # PAT Section
        tk.Label(root, text="PAT Name:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.pat_name_entry = tk.Entry(root, font=('Helvetica', 10))
        self.pat_name_entry.grid(row=0, column=1, padx=10, pady=5)

        tk.Label(root, text="PAT Secret:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        self.pat_secret_entry = tk.Entry(root, font=('Helvetica', 10), show="*")
        self.pat_secret_entry.grid(row=1, column=1, padx=10, pady=5)

        self.show_secret_button = tk.Button(root, text="Show Secret", command=self.toggle_show_secret, font=('Helvetica', 10))
        self.show_secret_button.grid(row=1, column=2, padx=10, pady=5)

        self.validate_button = tk.Button(root, text="Validate PAT", command=self.validate_pat, font=('Helvetica', 10))
        self.validate_button.grid(row=2, column=0, padx=10, pady=10)

        self.clear_all_button = tk.Button(root, text="Clear All", command=self.clear_all, font=('Helvetica', 10))
        self.clear_all_button.grid(row=2, column=1, padx=10, pady=10)

        self.save_pat_button = tk.Button(root, text="Save PAT", command=self.save_pat, font=('Helvetica', 10))
        self.save_pat_button.grid(row=3, column=0, columnspan=2, pady=5)

        # Choose PAT Section
        tk.Label(root, text="Choose a saved PAT:").grid(row=4, column=0, padx=10, pady=5, sticky="w")
        self.pat_combobox = ttk.Combobox(root, font=('Helvetica', 10))
        self.pat_combobox.grid(row=4, column=1, padx=10, pady=5)

        # Populate combobox with saved PATs
        if self.credentials:
            pat_names = [cred['pat_name'] for cred in self.credentials if isinstance(cred, dict)]
            self.pat_combobox['values'] = pat_names
            if pat_names:
                self.pat_combobox.current(0)  # Select the first one by default

        # Load PAT Details Section
        self.load_pat_button = tk.Button(root, text="Load PAT details", command=self.load_pat_details, font=('Helvetica', 10))
        self.load_pat_button.grid(row=5, column=0, columnspan=2, pady=5)

        # Delete PAT Section
        self.delete_pat_button = tk.Button(root, text="Delete PAT", command=self.delete_pat, font=('Helvetica', 10))
        self.delete_pat_button.grid(row=6, column=0, columnspan=2, pady=5)

        self.connection_label = tk.Label(root, text="", fg="green", font=('Helvetica', 10))
        self.connection_label.grid(row=7, column=0, columnspan=2, pady=5)

        # Load credentials if available
        if self.credentials and isinstance(self.credentials, list) and self.credentials:
            self.pat_name_entry.insert(0, self.credentials[0].get("pat_name", ""))
            self.pat_secret_entry.insert(0, self.credentials[0].get("pat_secret", ""))

    def toggle_show_secret(self):
        # Toggle visibility of PAT Secret
        if self.pat_secret_entry.cget("show") == "*":
            self.pat_secret_entry.config(show="")
            self.show_secret_button.config(text="Hide Secret")
        else:
            self.pat_secret_entry.config(show="*")
            self.show_secret_button.config(text="Show Secret")

    def validate_pat(self):
        pat_name = self.pat_name_entry.get()
        pat_secret = self.pat_secret_entry.get()
        if pat_name and pat_secret:
            result_message = validate_pat(pat_name, pat_secret)
            self.connection_label.config(text=result_message, fg="red" if "Invalid" in result_message else "green")
        else:
            messagebox.showerror("Error", "Please provide both PAT Name and Secret.")

    def save_pat(self):
        pat_name = self.pat_name_entry.get()
        pat_secret = self.pat_secret_entry.get()
        if pat_name and pat_secret:
            # First validate the PAT
            result_message = validate_pat(pat_name, pat_secret)
            if "Invalid" in result_message:
                messagebox.showerror("Error", "Invalid PAT token. Please validate the token before saving.")
                return

            try:
                save_credentials(pat_name, pat_secret)
                self.connection_label.config(text="PAT saved successfully!", fg="green")
                self.credentials = load_credentials()  # Reload credentials
                pat_names = [cred['pat_name'] for cred in self.credentials if isinstance(cred, dict)]
                self.pat_combobox['values'] = pat_names
                self.pat_combobox.current(0)
            except ValueError as e:
                messagebox.showerror("Error", str(e))
        else:
            messagebox.showerror("Error", "Please provide both PAT Name and Secret.")

    def load_pat_details(self):
        selected_pat_name = self.pat_combobox.get()
        if selected_pat_name:
            selected_pat = next((cred for cred in self.credentials if cred['pat_name'] == selected_pat_name), None)
            if selected_pat:
                self.pat_name_entry.delete(0, tk.END)
                self.pat_secret_entry.delete(0, tk.END)
                self.pat_name_entry.insert(0, selected_pat["pat_name"])
                self.pat_secret_entry.insert(0, selected_pat["pat_secret"])
        else:
            messagebox.showerror("Error", "No PAT selected for loading.")

    def delete_pat(self):
        selected_pat_name = self.pat_combobox.get()
        if selected_pat_name:
            self.credentials = [cred for cred in self.credentials if cred['pat_name'] != selected_pat_name]
            with open(CREDENTIALS_FILE, "w") as file:
                json.dump(self.credentials, file)
            self.pat_combobox['values'] = [cred['pat_name'] for cred in self.credentials]
            self.pat_combobox.set("")
            self.pat_name_entry.delete(0, tk.END)
            self.pat_secret_entry.delete(0, tk.END)
            self.connection_label.config(text=f"PAT '{selected_pat_name}' deleted successfully.", fg="red")
        else:
            messagebox.showerror("Error", "No PAT selected for deletion.")

    def clear_all(self):
        self.pat_name_entry.delete(0, tk.END)
        self.pat_secret_entry.delete(0, tk.END)
        self.connection_label.config(text="", fg="green")


# Run the app
if __name__ == "__main__":
    root = tk.Tk()
    app = TableauUserManager(root)
    root.mainloop()
