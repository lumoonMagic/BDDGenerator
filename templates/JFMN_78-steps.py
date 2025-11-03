from behave import given, when, then

from models.mssql_connector import MSSQLConnection
from models.rubrik import Rubrik
from models.utility import Utility

mssql = MSSQLConnection()
rubrik = Rubrik()
utility = Utility()

inserted_table_data = None
recovered_table_data = None
restore_time = None


# Scenario 1: Successful Backup
@given('MSSQL database version is {mssql_version}')
def step_impl(context, mssql_version):
    context.mssql_version = mssql_version

@given('Database is {database_name}')
def step_impl(context, database_name):
    context.database_name = database_name

@given('Table {table_name} is created on {server_ip}')
def step_impl(context, table_name, server_ip):
    context.table_name = table_name
    context.server_ip = server_ip

    create_table_result = mssql.create_table(server_ip, context.database_name, table_name)
    print(f"Table creation result: {create_table_result}")

@given('the platform is {platform}')
def step_impl(context, platform):
    context.platform = platform

@given('the OS is {os}')
def step_impl(context, os):
    context.os = os

@given('the sla id is {sla_id}')
def step_impl(context, sla_id):
    context.sla_id = sla_id

@given('the table {table_name} is inserted with first row of data')
def step_impl(context, table_name):
    backup_type = "Full backup"
    insert_data = mssql.insert_test_data(context.server_ip, context.database_name, context.table_name, backup_type)
    print(f"Data insertion into {table_name} result: {insert_data}")
    if insert_data.lower() == "test data inserted successfully":
        table_data = mssql.print_all_inserted(context.server_ip, context.database_name, context.table_name)
        print(f"Table data :-\n{table_data}")

@when('the method to trigger full database backup is called')
def step_impl(context):
    output = rubrik.get_mssql_db_id_details(context.database_name)
    db_id = output["data"]["mssqlDatabases"]["edges"][0]["node"]["id"]
    if context.sla_id.lower() == "invalid":
        db_id = "invalid_id"
    context.full_backup_status = rubrik.mssql_full_backup(db_id)

@then('the method returns trigger full backup status {trigger_backup_status}')
def step_impl(context, trigger_backup_status):
    print("Trigger Full Backup status:", context.full_backup_status)
    assert context.full_backup_status["status"] == trigger_backup_status, f"Expected {trigger_backup_status}, but got {context.full_backup_status['status']}"

@when('the method to get the full backup status is called')
def step_impl(context):
    global restore_time
    output = rubrik.get_mssql_db_id_details(context.database_name)
    db_id = output["data"]["mssqlDatabases"]["edges"][0]["node"]["id"]
    result = rubrik.get_activity_status(db_id, "BACKUP")
    status, info = result
    message = info['activityConnection']['nodes'][0]['message']
    object_name = info['objectName']
    last_updated = info['lastUpdated']
    progress = info['progress']
    severity = info['severity']
    cluster_name = info['clusterName']

    print(f"Backup Status: {status}")
    print(f"Object: {object_name}")
    print(f"Completed At: {last_updated}")
    print(f"Progress: {progress}")
    print(f"Severity: {severity}")
    print(f"Cluster: {cluster_name}")
    print(f"Details: {message}")

    if status.lower() == "success" or status.lower() == 'partial_success':
        context.final_full_backup_status = "Full backup successful"
        restore_time = utility.convert_utc_to_iso_format(utility.utc_time())
        print(f"Full backup completed at : {restore_time}")
    elif status.lower() == "failure" or status.lower() == "failed":
        context.final_full_backup_status = "Full backup failed"
    else:
        context.final_full_backup_status = status

@then('the method returns full backup status {backup_status}')
def step_impl(context, backup_status):
    assert context.final_full_backup_status == backup_status, f"Expected {backup_status}, but got {context.final_full_backup_status}"

# Scenario 2: Successful Restore

@given('MSSQL TDE enabled database {mssql_version} with {database_name} and {table_name} was backed up on {server_ip}')
def step_impl(context, mssql_version, database_name, table_name, server_ip):
    context.mssql_version = mssql_version
    context.database_name = database_name
    context.table_name = table_name
    context.server_ip = server_ip
    output = rubrik.get_mssql_db_id_details(context.database_name)
    context.db_id = output["data"]["mssqlDatabases"]["edges"][0]["node"]["id"]
    snapshot_output = rubrik.get_mssql_snapshot_id(context.db_id)
    context.snapshot_id_map = {
        "snapshot_id": snapshot_output['data']['mssqlDatabase']['cdmSnapshots']['nodes'][0]['id'],
        "recovery_date": snapshot_output['data']['mssqlDatabase']['cdmSnapshots']['nodes'][0]['date']}


@given('the snapshot id is {snapshot_id}')
def step_impl(context, snapshot_id):
    context.snapshot_id = snapshot_id


@when('the method to delete the table {table_name} is called')
def step_impl(context, table_name):
    context.delete_table_status = mssql.delete_table(context.server_ip, context.database_name, context.table_name)
    print(f"Table {table_name} deletion result: {context.delete_table_status}")

@then('the method returns table delete status {table_delete_status}')
def step_impl(context, table_delete_status):
    assert context.delete_table_status == table_delete_status, f"Expected {table_delete_status}, but got {context.delete_table_status}"


@when('the method to get the table {table_name} is called')
def step_impl(context, table_name):
    context.check_table_status = mssql.get_table(context.server_ip, context.database_name, context.table_name)
    print(f"Check Table {table_name} result: {context.check_table_status}")

@then('the method returns table status {check_table_status}')
def step_impl(context, check_table_status):
    assert context.check_table_status == check_table_status, f"Expected {check_table_status}, but got {context.check_table_status}"

@given('the target server ip is {target_server_ip}')
def step_impl(context, target_server_ip):
    context.target_server_ip = target_server_ip


# @when('the method to trigger full database restore is called')
# def step_impl(context):
#     snapshot_id_time = context.snapshot_id_map["recovery_date"]
#     if context.snapshot_id == "invalid":
#         context.db_id = "invalid_id"
#     context.restore_status = rubrik.restore_mssql_db(context.db_id, snapshot_id_time)
#     print(f"Trigger Restore status:", context.restore_status)

@when('the method to trigger full database restore with db_name {target_db} is called on {target_server_ip}')
def step_impl(context, target_db, target_server_ip):
    global restore_time
    output = rubrik.get_mssql_db_id_details(context.database_name)
    db_id = output["data"]["mssqlDatabases"]["edges"][0]["node"]["id"]
    target_instance_id = "f62e2ab7-24f7-51b0-9b51-783106cedcd5"
    target_database_name = target_db
    target_data_file_path = "F:\MSSQL2022\MSSQL16.MSSQLSERVER\MSSQL\Data"
    target_log_file_path = "G:\MSSQL2022\MSSQL16.MSSQLSERVER\MSSQL\Log"
    print(f"Restoring to target server IP: {target_server_ip}, target database: {target_database_name}, restore time: {restore_time}")
    context.restore_status = rubrik.mssql_export_restore(db_id, restore_time, target_instance_id, target_database_name, target_data_file_path, target_log_file_path)

@then('the method returns trigger full restore status {trigger_restore_status}')
def step_impl(context, trigger_restore_status):
    assert context.restore_status["status"] == trigger_restore_status, f"Expected {trigger_restore_status}, but got {context.restore_status['status']}"


@when('the method to get database full restore status is called')
def step_impl(context):
    output = rubrik.get_mssql_db_id_details(context.database_name)
    db_id = output["data"]["mssqlDatabases"]["edges"][0]["node"]["id"]
    result = rubrik.get_activity_status(db_id, "RECOVERY")
    status, info = result
    message = info['activityConnection']['nodes'][0]['message']
    object_name = info['objectName']
    last_updated = info['lastUpdated']
    progress = info['progress']
    severity = info['severity']
    cluster_name = info['clusterName']

    print(f"Restore Status: {status}")
    print(f"Object: {object_name}")
    print(f"Completed At: {last_updated}")
    print(f"Progress: {progress}")
    print(f"Severity: {severity}")
    print(f"Cluster: {cluster_name}")
    print(f"Details: {message}")

    if status.lower() == "success" or status.lower() == 'partial_success':
        context.final_restore_status = "Restore successful"
    elif status.lower() == "failure" or status.lower() == "failed":
        context.final_restore_status = "Restore failed"
    else:
        context.final_restore_status = status

@then('the method returns database full restore status {restore_status}')
def step_impl(context, restore_status):
    assert context.final_restore_status == restore_status, f"Expected {restore_status}, but got {context.final_restore_status}"


@when('the method to get the database {database_name} and get table {table_name} with table data is called')
def step_impl(context, database_name, table_name):
    context.db_exists_status = mssql.poll_for_database(context.server_ip, context.database_name)
    print(f"Database {database_name} exists status: {context.db_exists_status}")
    context.table_exists_status = mssql.poll_for_table(context.server_ip, context.database_name, context.table_name)
    print(f"Table {table_name} exists status: {context.table_exists_status}")

    global inserted_table_data
    global recovered_table_data
    table_data = mssql.print_all_inserted(context.server_ip, context.database_name, context.table_name)
    recovered_table_data = table_data
    print(f"Inserted Table Data:\n{inserted_table_data}\nRecovered Table Data:\n{recovered_table_data}")
    if inserted_table_data == recovered_table_data:
        context.table_data_status = "Table data matched"
    else:
        context.table_data_status = "Table data not matched"

@then('the method returns database exists status {db_exists_status}')
def step_impl(context, db_exists_status):
    assert context.db_exists_status == db_exists_status, f"Expected {db_exists_status}, but got {context.db_exists_status}"

@then('the method returns table exists status {table_exists}')
def step_impl(context, table_exists):
    assert context.table_exists_status == table_exists, f"Expected {table_exists}, but got {context.table_exists_status}"

@then('the method returns table data status {table_data_status} to match the inserted data')
def step_impl(context, table_data_status):
    assert context.table_data_status == table_data_status, f"Expected {table_data_status}, but got {context.table_data_status}"
