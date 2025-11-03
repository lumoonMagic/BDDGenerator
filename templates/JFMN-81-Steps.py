from behave import given, when, then
from models.oracle_connector import OracleConnection
from models.oracle_rubrik import Rubrik

oracle = OracleConnection()
rubrik = Rubrik()


# Scenario 1: Perform Successful Full Backup for Oracle Database
@given('Oracle database {database_name} with version <oracle_version> on {server_ip}')
def step_impl(context, database_name , server_ip):
    context.database_name = database_name
    context.server_ip = server_ip

@given('the platform is {platform}')
def step_impl(context, platform , platform):
    context.platform = platform

@given('the OS is {os}')
def step_impl(context, os , os):
    context.os = os
@given('the SLA ID is {sla_id}')
def step_impl(context, sla_id , sla_id):
    context.sla_id = sla_id

    @when('the method to trigger full database backup is called')
    

@given('Database {database_name} with {table_name} is created on {server_ip}')
def step_impl(context, database_name, table_name, server_ip):
    context.database_name = database_name
    context.table_name = table_name
    context.server_ip = server_ip

    # Create PDB (Pluggable Database)
    create_pdb_result = oracle.create_pdb(server_ip, database_name)
    print(f"PDB creation result: {create_pdb_result}")

    # Create table in the PDB
    create_table_result = oracle.create_table(server_ip, table_name)
    print(f"Table creation result: {create_table_result}")

    # Insert test data into the table
    insert_result = oracle.insert(server_ip, table_name)
    print(f"Test data insertion result: {insert_result}")


@given('the platform is {platform}')
def step_impl(context, platform):
    context.platform = platform


@given('the OS is {os}')
def step_impl(context, os):
    context.os = os


@when('the method to trigger full database backup is called')
def step_impl(context):
    output = rubrik.get_oracle_db_id(context.database_name)
    db_id = output["response"]["data"]["oracleDatabases"]["edges"][0]["node"]["id"]
    context.backup_status = rubrik.oracle_backup(db_id)


@then('the method returns status {trigger_status}')
def step_impl(context, trigger_status):
    if hasattr(context, "backup_status"):
        assert context.backup_status["status"] == trigger_status
    elif hasattr(context, "archive_log_backup_status"):
        assert context.archive_log_backup_status["status"] == trigger_status
    elif hasattr(context, "delete_db_status"):
        assert context.delete_db_status == trigger_status
    elif hasattr(context, "check_db_status"):
        assert context.check_db_status == trigger_status
    elif hasattr(context, "pitr_restore_status"):
        assert context.pitr_restore_status["status"] == trigger_status
    elif hasattr(context, "archive_log_restore_status"):
        assert context.archive_log_restore_status["status"] == trigger_status
    elif hasattr(context, "logs_deletion_status"):
        assert context.logs_deletion_status == trigger_status


@when('the method to get the full database backup status is called')
def step_impl(context):
    output = rubrik.get_oracle_db_id(context.database_name)
    db_id = output["response"]["data"]["oracleDatabases"]["edges"][0]["node"]["id"]
    result = rubrik.get_activity_status(db_id, "BACKUP")
    status, info = result

    print(f"Backup Status: {status}")
    print(f"Details: {info}")

    if status.lower() == "success":
        context.final_backup_status = "Backup successful"
    else:
        context.final_backup_status = "Backup failed"


@then('the method returns backup status {backup_status}')
def step_impl(context, backup_status):
    assert context.final_backup_status == backup_status


@when('the method to trigger archive log backup is called')
def step_impl(context):
    output = rubrik.get_oracle_db_id(context.database_name)
    db_id = output["response"]["data"]["oracleDatabases"]["edges"][0]["node"]["id"]
    context.archive_log_backup_status = rubrik.oracle_archive_log_backup(db_id)


@when('the method to get the archive log backup status is called')
def step_impl(context):
    output = rubrik.get_oracle_db_id(context.database_name)
    db_id = output["response"]["data"]["oracleDatabases"]["edges"][0]["node"]["id"]
    result = rubrik.get_activity_status(db_id, "LOG_BACKUP")
    status, info = result

    print(f"Archive Log Backup Status: {status}")
    print(f"Details: {info}")

    if status.lower() == "success":
        context.final_archive_log_backup_status = "Backup successful"
    else:
        context.final_archive_log_backup_status = "Backup failed"


@then('the method returns backup status {archive_log_status}')
def step_impl(context, archive_log_status):
    assert context.final_archive_log_backup_status == archive_log_status


# Scenario 2: Point-in-Time Restore Steps
@given('Database {database_name} with {table_name} was backed up on {server_ip}')
def step_impl(context, database_name, table_name, server_ip):
    context.database_name = database_name
    context.table_name = table_name
    context.server_ip = server_ip


@when('the method to delete the database is called')
def step_impl(context):
    context.delete_db_status = oracle.drop_pdb(context.server_ip, context.database_name)


@then('the method returns status {db_delete_status}')
def step_impl(context, db_delete_status):
    assert context.delete_db_status == db_delete_status


@when('the method to get the database is called')
def step_impl(context):
    context.check_db_status = oracle.get_database(context.server_ip, context.database_name)


@then('the method returns status {check_db_status}')
def step_impl(context, check_db_status):
    assert context.check_db_status == check_db_status


@when('the method to delete the archive log is called')
def step_impl(context):
    log_file = "   "  # This should come from config or context
    context.logs_deletion_status = oracle.delete_archive_logs(context.server_ip, log_file)


@then('the method returns status {log_deletion_status}')
def step_impl(context, log_deletion_status):
    assert context.logs_deletion_status == log_deletion_status


@when('the method to check archive log existence is called')
def step_impl(context):
    log_file = " "  # This should come from config or context
    context.archive_logs_check_status = oracle.check_archive_log_status(context.server_ip, log_file)


@then('the method returns {check_log_status}')
def step_impl(context, check_log_status):
    assert context.archive_logs_check_status == check_log_status


@when('the method to trigger Point-in-Time restore is called with point-in-time {restore_time}')
def step_impl(context, restore_time):
    # TODO: Implement Point-in-Time restore functionality
    # This step should trigger PITR with the specified restore_time
    pass


@then('the method returns status {pitr_trigger_status}')
def step_impl(context, pitr_trigger_status):
    # TODO: Implement assertion for PITR trigger status
    pass


@when('the method to get the Point-in-Time restore status is called')
def step_impl(context):
    # TODO: Implement getting PITR status
    pass


@then('the method returns restore status {restore_db_status}')
def step_impl(context, restore_db_status):
    # TODO: Implement assertion for PITR restore status
    pass


@when('the method to trigger archive log restore is called')
def step_impl(context):
    output = rubrik.get_oracle_db_id(context.database_name)
    db_id = output["response"]["data"]["oracleDatabases"]["edges"][0]["node"]["id"]
    target_host_id = "target-host-id"  # This should come from config or context
    target_mount_path = "/mount/path"  # This should come from config or context
    start_time = "2025-09-24T00:00:00Z"  # This should come from config or context
    end_time = "2025-09-25T00:00:00Z"  # This should come from config or context
    context.archive_log_restore_status = rubrik.oracle_archive_log_restore(
        db_id, target_host_id, target_mount_path, start_time, end_time
    )


@then('the method returns status {trigger_archivelog_restore}')
def step_impl(context, trigger_archivelog_restore):
    assert context.archive_log_restore_status["status"] == trigger_archivelog_restore


@when('the method to get archive log restore is called')
def step_impl(context):
    output = rubrik.get_oracle_db_id(context.database_name)
    db_id = output["response"]["data"]["oracleDatabases"]["edges"][0]["node"]["id"]
    result = rubrik.get_activity_status(db_id, "LOG_RECOVERY")
    status, info = result

    print(f"Archive Log Restore Status: {status}")
    print(f"Details: {info}")

    if status.lower() == "success":
        context.final_archive_log_restore_status = "Restore successful"
    else:
        context.final_archive_log_restore_status = "Restore failed"


@then('the method returns status {archive_log_restore_status}')
def step_impl(context, archive_log_restore_status):
    assert context.final_archive_log_restore_status == archive_log_restore_status


@when('the method to get the database and get table is called')
def step_impl(context):
    context.db_exists_status = oracle.get_database(context.server_ip, context.database_name)
    context.table_exists_status = oracle.get_table_status(context.server_ip, context.table_name)


@then('the method returns status {db_exists_status}')
def step_impl(context, db_exists_status):
    assert context.db_exists_status == db_exists_status


@then('the method returns status {table_exists_status} for {table_name}')
def step_impl(context, table_exists_status, table_name):
    assert context.table_exists_status == table_exists_status


@when('the method to check archive log existence is called after restore')
def step_impl(context):
    log_file = "path-to-archive-log"  # This should come from config or context
    context.archive_logs_after_restore_status = oracle.check_archive_log_status(context.server_ip, log_file)


@then('the method returns {archive_log_exists} for {database_name}')
def step_impl(context, archive_log_exists, database_name):
    assert context.archive_logs_after_restore_status == archive_log_exists


# Scenario 3 & 4: Failure Scenarios
@given('the database service status is {db_service_status}')
def step_impl(context, db_service_status):
    context.database_service_status = db_service_status


@given('the rubrik agent status is {agent_status}')
def step_impl(context, agent_status):
    context.agent_status = agent_status


@given('Oracle database {oracle_version} with {database_name} and {table_name} was backed up on {server_ip}')
def step_impl(context, oracle_version, database_name, table_name, server_ip):
    context.oracle_version = oracle_version
    context.database_name = database_name
    context.table_name = table_name
    context.server_ip = server_ip


@given('the restore id is {restore_id}')
def step_impl(context, restore_id):
    context.restore_id = restore_id


@when('the method to get the restore status is called')
def step_impl(context):
    # TODO: Implement getting general restore status
    pass


@then('the method returns status {archivelog_restore_status}')
def step_impl(context, archivelog_restore_status):
    # TODO: Implement assertion for archivelog restore status
    pass


# Scenario 5: Invalid Point-in-Time Restore (Outside Backup Range)
@given('the backup type is {backup_type} taken at {backup_time}')
def step_impl(context, backup_type, backup_time):
    context.backup_type = backup_type
    context.backup_time = backup_time


@when('the method to trigger Point-in-Time restore is called with restore time {restore_time} outside the backup range')
def step_impl(context, restore_time):
    # TODO: Implement PITR with invalid time range
    pass


@then('the method returns error message {error_message}')
def step_impl(context, error_message):
    # TODO: Implement assertion for error message
    pass