import json
import requests

def fetch_google_api_specs():
    """Fetches all Google OpenAPI specs from APIs.guru and saves them as a list of HttpProvider-like objects."""
    print("Fetching API list from APIs.guru...")
    response = requests.get("https://api.apis.guru/v2/list.json")
    response.raise_for_status()  # Raise an exception for bad status codes
    all_apis = response.json()

    google_providers = []
    print("Filtering for Google APIs...")

    for api_id, api_data in all_apis.items():
        if api_id.startswith("googleapis.com"):
            preferred_version = api_data.get("preferred")
            if preferred_version and preferred_version in api_data.get("versions", {}):
                version_data = api_data["versions"][preferred_version]
                swagger_url = version_data.get("swaggerUrl")
                if swagger_url:
                    provider = {
                        "name": api_id.replace(".", "_"),
                        "provider_type": "http",
                        "http_method": "GET",
                        "url": swagger_url,
                        "content_type": "application/json",
                        "auth": None,
                        "headers": None,
                        "body_field": "body",
                        "header_fields": None
                    }
                    google_providers.append(provider)

    output_filename = "google_apis.json"
    print(f"Found {len(google_providers)} Google API specs. Saving to {output_filename}...")
    with open(output_filename, "w") as f:
        json.dump(google_providers, f, indent=2)

    print(f"Successfully saved Google API specs to {output_filename}")

if __name__ == "__main__":
    fetch_google_api_specs()
