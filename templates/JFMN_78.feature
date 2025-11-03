Feature: MSSQL TDE Database Full Backup & Restore on same and different windows server using Rubrik

  Scenario Outline: [1] Perform Successful MSSQL Backup on TDE Enabled Database
    Given MSSQL database version is <mssql_version>
    And TDE enabled Database is <database_name>
    And the platform is <platform>
    And the OS is <os>
    And the sla id is <sla_id>
    And Table <table_name> is created on <server_ip>
    And the table <table_name> is inserted with first row of data
    When the method to trigger full database backup is called
    Then the method returns trigger full backup status <trigger_backup_status>
    When the method to get the full backup status is called
    Then the method returns full backup status <backup_status>
    Examples:
      | server_ip    | platform   | os           | sla_id | database_name | table_name      | mssql_version | trigger_backup_status | backup_status          |
      | 10.81.91.111 | IAAS (AWS) | Windows 2022 | valid  | SDLC_78_2022  | test_table_2022 | 2022          | Full backup triggered | Full backup successful |

#  Scenario Outline: [2] Perform Successful MSSQL Restore on same server
#    Given MSSQL TDE enabled database <mssql_version> with <database_name> and <table_name> was backed up on <server_ip>
#    And the platform is <platform>
#    And the OS is <os>
#    And the snapshot id is <snapshot_id>
#    When the method to delete the table <table_name> is called
#    Then the method returns table delete status <table_delete_status>
#    When the method to get the table <table_name> is called
#    Then the method returns table status <check_table_status>
#    When the method to trigger full database restore is called
#    Then the method returns trigger full restore status <trigger_restore_status>
#    When the method to get database full restore status is called
#    Then the method returns database full restore status <restore_status>
#    When the method to get the database <database_name> and get table <table_name> with table data is called
#    Then the method returns database exists status <db_exists_status>
#    And the method returns table exists status <table_exists>
#    And the method returns table data status <table_data_status> to match the inserted data
#    Examples:
#      | server_ip    | platform  | os           | snapshot_id | database_name | table_name      | mssql_version | table_delete_status           | check_table_status                   | trigger_restore_status | restore_status     | db_exists_status             | table_exists                 | table_data_status  |
#      | 10.81.91.111 | IAAS(AWS) | Windows 2022 | valid       | SDLC_78_2022  | test_table_2022 | 2022          | Table test_table_2022 deleted | Table test_table_2022 does not exist | Restore triggered      | Restore successful | Database SDLC_78_2022 exists | Table test_table_2022 exists | Table data matched |

  Scenario Outline: [3] Perform Successful MSSQL Restore on different server
    Given MSSQL TDE enabled database <mssql_version> with <database_name> and <table_name> was backed up on <server_ip>
    And the platform is <platform>
    And the OS is <os>
    And the snapshot id is <snapshot_id>
    And the target server ip is <target_server_ip>
    When the method to trigger full database restore with db_name <target_db> is called on <target_server_ip>
    Then the method returns trigger full restore status <trigger_restore_status>
    When the method to get database full restore status is called
    Then the method returns database full restore status <restore_status>
    When the method to get the database <target_db> and get table <table_name> with table data is called
    Then the method returns database exists status <db_exists_status>
    And the method returns table exists status <table_exists>
    And the method returns table data status <table_data_status> to match the inserted data
    Examples:
      | server_ip    | platform  | os           | snapshot_id | database_name | table_name      | mssql_version | target_server_ip | trigger_restore_status | restore_status     | target_db        | db_exists_status                 | table_exists                 | table_data_status  |
      | 10.81.91.111 | IAAS(AWS) | Windows 2022 | valid       | SDLC_78_2022  | test_table_2022 | 2022          | 10.81.203.37     | Restore triggered      | Restore successful | SDLC_78_EXPORTED | Database SDLC_78_EXPORTED exists | Table test_table_2022 exists | Table data matched |


#  Scenario Outline: [4] Perform MSSQL Backup Failure Scenario
#    Given MSSQL database version is <mssql_version>
#    And Database is <database_name>
#    And the platform is <platform>
#    And the OS is <os>
#    And the sla id is <sla_id>
#    And Table <table_name> is created on <server_ip>
#    And the table <table_name> is inserted with first row of data
#    When the method to trigger database t-log backup is called
#    Then the method returns trigger t-log backup status <trigger_tlog_backup_status>
#    Then the table <table_name> is inserted with second row of data
#    When the method to trigger full database backup is called
#    Then the method returns trigger full backup status <trigger_backup_status>
#    Examples:
#      | server_ip    | platform   | os           | sla_id  | database_name | table_name      | mssql_version | trigger_tlog_backup_status  | trigger_backup_status      |
#      | 10.81.91.111 | IAAS (AWS) | Windows 2022 | invalid | SDLC_78_2022  | test_table_2022 | 2022          | T-log backup trigger failed | Full backup trigger failed |
#
#
#  Scenario Outline: [5] Perform MSSQL Restore Failure Scenario
#    Given MSSQL database <mssql_version> with <database_name> and <table_name> was backed up on <server_ip>
#    And the platform is <platform>
#    And the OS is <os>
#    And the snapshot id is <snapshot_id>
#    When the method to delete the table <table_name> is called
#    Then the method returns table delete status <table_delete_status>
#    When the method to get the table <table_name> is called
#    Then the method returns table status <check_table_status>
#    When the method to trigger full database restore is called
#    Then the method returns trigger full restore status <trigger_restore_status>
#    Examples:
#      | server_ip    | platform  | os           | snapshot_id | database_name | table_name      | mssql_version | table_delete_status           | check_table_status                   | trigger_restore_status |
#      | 10.81.91.111 | IAAS(AWS) | Windows 2022 | invalid     | SDLC_78_2022  | test_table_2022 | 2022          | Table test_table_2022 deleted | Table test_table_2022 does not exist | Restore trigger failed |
