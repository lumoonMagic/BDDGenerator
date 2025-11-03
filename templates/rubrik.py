import configparser
import datetime
import json
import os
import time

import requests


from models.utility import Utility
from pathlib import Path
from datetime import date, timedelta
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class Rubrik:

    def __init__(self):

        self.current_working_directory = os.getcwd()
        self.config_file_path = os.path.join(self.current_working_directory, "config")
        self.config_file = os.path.join(self.config_file_path, "main_config.ini")
        self.config = configparser.ConfigParser()
        self.config.read(self.config_file)

        if not os.path.exists(self.config_file):
            raise FileNotFoundError(f"Config file not found: {self.config_file}")
        self.graph_url = self.config["rubrik"]["graph_url"]
        self.client_id = self.config["rubrik"]["client_id"]

    def create_token(self):
        token_url = self.config["rubrik"]["token_url"]

        client_secret = Utility.decode(self.config["rubrik"]["client_secret"])
        payload = json.dumps({
            "client_id": self.client_id,
            "client_secret": client_secret
        })
        headers = {
            'Content-Type': 'application/json'
        }
        msg = f"To generate token for Rubrik authentication calling POST API {token_url}"
        response = requests.post(url=token_url, headers=headers, data=payload, verify=False)
        if response.status_code == 200:
            token = response.json()["access_token"]
            return token
        else:
            msg = f"Failed to create Rubrik authentication token.\n" \
                  f"API response status code :- {response.status_code}\n" \
                  f"API response :- {response.text}"
            raise Exception(msg)

    def _load_json_payload(self, json_filename: str) -> dict:

        file_path = Path(self.current_working_directory) / "data" / json_filename
        try:
            with file_path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            raise FileNotFoundError(f"File {json_filename} does not exist in 'data' folder")

    def get_recent_events(self, db_id: str, activity_type: str)-> dict:
        """
        Method to fetch recent events for a given database ID and activity type.
        Args:
            db_id (str): The ID of the database to fetch events for.
            activity_type (str): The type of activity to filter events by.
        Returns:
            dict: A dictionary containing the status and response of the recent events fetch operation.
        """
        recent_events_json = self.config["rubrik"]["get_recent_event_query"]
        payload = self._load_json_payload(recent_events_json)
        payload["variables"]["filters"]["objectFid"] = [db_id]
        payload["variables"]["filters"]["lastActivityType"] = activity_type

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.create_token()}"
        }
        payload = json.dumps(payload)
        response = requests.post(url=self.graph_url, headers=headers, data=payload, verify=False)
        msg = {"response": response.text}

        if response.status_code in [200, 201, 202]:
            error = response.json().get("errors", [])
            if error:
                msg.update({"script_status": "failed to get recent events"})
                msg.update({"response": error})
            else:
                msg.update({"script_status": "Successfully fetched recent events"})
        else:
            msg.update({"status": "failed to get recent events"})
            raise Exception(msg)
        return msg

    def get_activity_status(self, db_id: str, activity_type: str, max_wait=360):

        elapsed = 0
        poll_interval = 30

        while elapsed < max_wait:
            result = self.get_recent_events(db_id, activity_type)
            response_data = json.loads(result["response"])
            try:
                node = response_data['data']['activitySeriesConnection']['edges'][0]['node']
                status = node['lastActivityStatus']
                print(status)
                if status.lower() == 'failed' or status.lower() == 'failure':
                    print(f"{activity_type} failed.")
                    return status, node
                if status.lower() == 'success' or status.lower() == 'partial_success':
                    print(f"{activity_type} completed successfully.")
                    return status, node

            except (KeyError, IndexError):
                print(f"No {activity_type} event found yet.")

            time.sleep(poll_interval)
            elapsed += poll_interval

        raise TimeoutError(f"{activity_type} did not complete within the maximum wait time.")

    def get_mssql_db_id_details(self, db_name):

        query_file = self.config["rubrik"]["get_mssql_database_id"]
        payload = self._load_json_payload(query_file)
        payload["variables"]["filter"][0]["texts"] = db_name
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.create_token()}"
        }

        # Make the request
        response = requests.post(url=self.graph_url, headers=headers, data=json.dumps(payload), verify=False)

        if response.status_code in [200, 201, 202]:
            json_response = response.json()
            errors = json_response.get("errors")
            if errors:
                raise Exception(f"GraphQL error: {errors}")
            return json_response
        else:
            raise Exception(
                f"Failed to mssql db Id. Status Code: {response.status_code}. Response: {response.text}")

    def get_mssql_snapshot_id(self, mssql_database_id: str) -> dict:
        mssql_snapshot_id_json = self.config["rubrik"]["get_mssql_snapshot_id"]
        payload = self._load_json_payload(mssql_snapshot_id_json)
        payload["variables"]["databaseFid"] = mssql_database_id

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.create_token()}"
        }
        payload = json.dumps(payload)
        msg = f"To get MSSQL Snapshot ID calling POST API :- {self.graph_url}\nData :- {payload}"
        print(msg)
        response = requests.post(url=self.graph_url, headers=headers, data=payload, verify=False)
        if response.status_code in [200, 201, 202]:
            error = response.json().get("errors", [])
            if error:
                msg = f"Failed to get MSSQL Snapshot ID for database ID {mssql_database_id}"
                msg += f"\nResponse :- {error}"
                raise Exception(msg)
            else:
                db_snapshot_details = response.json()
                return db_snapshot_details
        else:
            msg = f"Failed to get MSSQL Snapshot ID for database ID {mssql_database_id}\n" \
                  f"Response status code :- {response.status_code}\n" \
                  f"Response :- {response.text}"
            raise Exception(msg)

    def mssql_full_backup(self, mssql_db_id: str) -> dict:
        try:
            mssql_db_backup_json = self.config["rubrik"]["mssql_full_backup_json"]
            payload = self._load_json_payload(mssql_db_backup_json)

            payload["variables"]["input"]["id"] = mssql_db_id
            payload["variables"]["input"]["config"]["baseOnDemandSnapshotConfig"]["slaId"] = self.config["rubrik"]["mssql_sla_id"]
            print("Backup payload being sent:\n", json.dumps(payload, indent=2))
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.create_token()}"
            }
            payload = json.dumps(payload)
            msg = f"To backup Full MSSQL DB calling POST API :- {self.graph_url}\nData :- {payload}"
            print(msg)
            response = requests.post(url=self.graph_url, headers=headers, data=payload, verify=False)
            msg = {"response": response.text}
            if response.status_code in [200, 201, 202]:
                print("Response JSON:", response.json())
                error = response.json().get("errors", [])
                print("Errors from API:", error)

                if error:
                    msg.update({"status": f"Backup trigger failed"})
                    msg.update({"response": error})
                else:
                    msg.update({"status": f"Backup triggered"})
            else:
                msg.update({"status": f"Backup trigger failed"})
                raise Exception(msg)
        except Exception as e:
            print(f"An error occurred during full backup: {e}")
            msg = {"status": f"Backup trigger failed", "error": str(e)}
        return msg

    def mssql_incremental_backup(self, mssql_db_id: str) -> dict:
        try:
            mssql_db_backup_json = self.config["rubrik"]["mssql_db_backup_json"]
            payload = self._load_json_payload(mssql_db_backup_json)
            payload["variables"]["input"]["config"]["databaseIds"] = mssql_db_id
            payload["variables"]["input"]["config"]["baseOnDemandSnapshotConfig"]["slaId"] = self.config["rubrik"]["mssql_sla_id"]
            print("Backup payload being sent:\n", json.dumps(payload, indent=2))
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.create_token()}"
            }
            payload = json.dumps(payload)
            msg = f"To backup Full MSSQL DB calling POST API :- {self.graph_url}\nData :- {payload}"
            print(msg)
            response = requests.post(url=self.graph_url, headers=headers, data=payload, verify=False)
            msg = {"response": response.text}
            if response.status_code in [200, 201, 202]:
                print("Response JSON:", response.json())
                error = response.json().get("errors", [])
                print("Errors from API:", error)

                if error:
                    msg.update({"status": f"Backup trigger failed"})
                    msg.update({"response": error})
                else:
                    msg.update({"status": f"Incremental backup triggered"})
            else:
                msg.update({"status": f"Backup trigger failed"})
                raise Exception(msg)
        except Exception as e:
            print(f"An error occurred during full backup: {e}")
            msg = {"status": f"Backup trigger failed", "error": str(e)}
        return msg

    def mssql_tlog_backup(self, mssql_db_id: str) -> dict:
        try:
            mssql_db_backup_json = self.config["rubrik"]["mssql_tlog_backup_json"]
            payload = self._load_json_payload(mssql_db_backup_json)
            print(mssql_db_id)
            payload["variables"]["input"]["id"] = mssql_db_id
            print("Backup payload being sent:\n", json.dumps(payload, indent=2))
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.create_token()}"
            }
            payload = json.dumps(payload)
            msg = f"To backup Full MSSQL DB calling POST API :- {self.graph_url}\nData :- {payload}"
            print(msg)
            response = requests.post(url=self.graph_url, headers=headers, data=payload, verify=False)
            msg = {"response": response.text}
            if response.status_code in [200, 201, 202]:
                print("Response JSON:", response.json())
                error = response.json().get("errors", [])
                print("Errors from API:", error)

                if error:
                    msg.update({"status": f"T-log backup triggered"})
                    msg.update({"response": error})
                else:
                    msg.update({"status": f"T-log backup triggered"})
            else:
                msg.update({"status": f"Backup trigger failed"})
                raise Exception(msg)
        except Exception as e:
            print(f"An error occurred during Tlog backup: {e}")
            msg = {"status": "Backup trigger failed", "error": str(e)}
        return msg

    def restore_mssql_db(self, db_id: str, snapshot_id_timedb: str) -> dict:

        try:

            # Load the JSON template for MSSQL restore
            mssql_db_restore_file = self.config["rubrik"]["mssql_db_restore_json"]
            payload = self._load_json_payload(mssql_db_restore_file)

            epoch_miliseconds = Utility.utc_to_epoch_ms(snapshot_id_timedb)
            # Update payload with provided values
            payload["variables"]["input"]["id"] = db_id
            payload["variables"]["input"]["config"]["recoveryPoint"]["timestampMs"] = epoch_miliseconds
            print(f"Epoch milliseconds for snapshot time {snapshot_id_timedb}: {epoch_miliseconds}")
            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.create_token()}"
            }

            # Convert payload to string
            payload_str = json.dumps(payload)
            print(f"To restore MSSQL Full DB calling POST API :- {self.graph_url}\nData :- {payload_str}")

            # Send the restore request
            response = requests.post(url=self.graph_url, headers=headers, data=payload_str, verify=False)

            # Build response message
            msg = {"response": response.text}
            if response.status_code in [200, 201, 202]:
                error = response.json().get("errors", [])
                if error:
                    msg.update({"status": "Restore trigger failed"})
                    msg.update({"response": error})
                else:
                    msg.update({"status": "Restore triggered"})
            else:
                msg.update({"status": "Restore trigger failed"})
                raise Exception(msg)

            return msg
        except Exception as e:
            raise Exception(f"An error occurred during restore: {e}")

    def refresh_mssql_physical_host(self, mssql_physical_host_id: str) -> dict:
        host_refresh_json = self.config["rubrik"]["mssql_host_refresh_query"]
        payload = self._load_json_payload(host_refresh_json)
        payload["variables"]["id"] = mssql_physical_host_id

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.create_token()}"
        }
        payload = json.dumps(payload)
        msg = f"To refresh mssql physical host calling POST API :- {self.graph_url}\nData :- {payload}"
        print(msg)
        response = requests.post(url=self.graph_url, headers=headers, data=payload, verify=False)
        if response.status_code in [200, 201, 202]:
            error = response.json().get("errors", [])
            if error:
                msg = f"Failed to refresh mssql physical host for ID {mssql_physical_host_id}"
                msg += f"\nResponse :- {error}"
                raise Exception(msg)
            else:
                host_refresh_details = response.json()
                return host_refresh_details
        else:
            msg = f"Failed to refresh mssql physical host for ID {mssql_physical_host_id}\n" \
                  f"Response status code :- {response.status_code}\n" \
                  f"Response :- {response.text}"
            raise Exception(msg)

    def mssql_export_restore(self, db_id, restore_time, target_instance_id, target_database_name, target_data_file_path, target_data_filename, target_log_file_path, target_log_filename, logical_name):
        try:

            # Load the JSON template for MSSQL restore
            mssql_db_restore_file = self.config["rubrik"]["mssql_export_restore_json"]
            payload = self._load_json_payload(mssql_db_restore_file)
            epoch_miliseconds = Utility.utc_to_epoch_ms(restore_time)
            print(f"Epoch milliseconds for snapshot time {restore_time}: {epoch_miliseconds}")
            # Set all required variables from parameters
            payload["variables"]["input"]["id"] = db_id
            payload["variables"]["input"]["config"]["recoveryPoint"]["timestampMs"] = epoch_miliseconds
            payload["variables"]["input"]["config"]["targetInstanceId"] = target_instance_id
            payload["variables"]["input"]["config"]["targetDatabaseName"] = target_database_name
            payload["variables"]["input"]["config"]["targetFilePaths"][0]["exportPath"] = target_data_file_path
            payload["variables"]["input"]["config"]["targetFilePaths"][0]["newFilename"] = target_data_filename
            payload["variables"]["input"]["config"]["targetFilePaths"][0]["logicalName"] = logical_name
            payload["variables"]["input"]["config"]["targetFilePaths"][1]["exportPath"] = target_log_file_path
            payload["variables"]["input"]["config"]["targetFilePaths"][1]["newFilename"] = target_log_filename
            payload["variables"]["input"]["config"]["targetFilePaths"][1]["logicalName"] = f"{logical_name}_log"


            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.create_token()}"
            }

            payload_str = json.dumps(payload)
            print(f"To restore MSSQL Export DB calling POST API :- {self.graph_url}\nExport payload being sent:\n {json.dumps(payload, indent=2)}")
            response = requests.post(url=self.graph_url, headers=headers, data=payload_str, verify=False)

            msg = {"response": response.text}
            if response.status_code in [200, 201, 202]:
                error = response.json().get("errors", [])
                if error:
                    msg.update({"status": "Restore trigger failed"})
                    msg.update({"response": error})
                else:
                    msg.update({"status": "Restore triggered"})
            else:
                msg.update({"status": "Restore trigger failed"})
                raise Exception(msg)

            return msg
        except Exception as e:
            raise Exception(f"An error occurred during restore: {e}")

    def list_mssql_dbs_by_host(self, hostname: str) -> dict:
        """
        List all MSSQL databases for a given host.
        Args:
            hostname (str): The hostname to filter MSSQL databases.
        Returns:
            dict: The response from the Rubrik API containing MSSQL databases for the host.
        """
        query_file = self.config["rubrik"]["list_all_mssql_dbs_query"]
        payload = self._load_json_payload(query_file)
        payload['variables']['hostFilter'][0]['texts'] = [hostname]
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.create_token()}"
        }
        payload_str = json.dumps(payload)
        response = requests.post(url=self.graph_url, headers=headers, data=payload_str, verify=False)
        if response.status_code == 200:
            return response.json()
        else:
            msg = f"Failed to list MSSQL DBs for host {hostname}. Status: {response.status_code}, Response: {response.text}"
            print(msg)
            raise Exception(msg)

    def parse_mssql_response(self, hostname):
        """
        Parses the JSON dictionary from the Rubrik GraphQL query and prints a summary.

        Args:
            hostname (str): hostname.
        """
        try:
            data = self.list_mssql_dbs_by_host(hostname)
            hosts = data['data']['mssqlTopLevelDescendants']['edges']
        except KeyError as e:
            print(f"Error: Could not find expected key '{e}' in JSON data. Please check the response structure.")
            return

        results = []
        for host_edge in hosts:
            host_node = host_edge.get('node', {})
            if not host_node:
                continue

            host_info = {
                "Hostname": host_node.get('name', 'N/A'),
                "HostFID": host_node.get('id', 'N/A')
            }

            databases = host_node.get('databaseDescendantConnection', {}).get('edges', [])

            instances = {}
            database_list = []

            for db_edge in databases:
                db_node = db_edge.get('node', {})
                if not db_node:
                    continue

                if db_node.get('slaAssignment') == 'Derived':
                    instance_source = db_node.get('effectiveSlaSourceObject', {})
                    instance_name = instance_source.get('name')

                    if instance_name and instance_name not in instances:
                        instance_sla = db_node.get('effectiveSlaDomain', {})
                        instances[instance_name] = {
                            'fid': instance_source.get('fid', 'N/A'),
                            'sla_id': instance_sla.get('id', 'N/A'),
                            'sla_name': instance_sla.get('name', 'N/A')
                        }

                db_info = {
                    'DBname': db_node.get('name', 'N/A'),
                    'DBFID': db_node.get('id', 'N/A'),
                    'SLAFID': db_node.get('effectiveSlaDomain', {}).get('id', 'N/A'),
                    'SLANAME': db_node.get('effectiveSlaDomain', {}).get('name', 'N/A')
                }
                database_list.append(db_info)

            db_info = {
                'DBname': db_node.get('name', 'N/A'),
                'DBFID': db_node.get('id', 'N/A'),
                'SLAFID': db_node.get('effectiveSlaDomain', {}).get('id', 'N/A'),
                'SLANAME': db_node.get('effectiveSlaDomain', {}).get('name', 'N/A')
            }
            database_list.append(db_info)
            results.append({
                "Host": host_info,
                "Instances": instances,
                "Databases": database_list,
                "InstanceCount": len(instances),
                "DatabaseCount": len(database_list)
            })
            return results


    @staticmethod
    def get_past_date(days_ago=0):
        """
        Returns the date 'days_ago' days before today.
        If no argument is provided, returns today's date.
        """
        return date.today() - timedelta(days=days_ago)

    def get_db_id_by_name(self, hostname, db_name):
        data = self.parse_mssql_response(hostname)
        for db in data[0]['Databases']:
            if db['DBname'] == db_name:
                return db['DBFID']
        return None