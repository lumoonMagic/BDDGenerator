Feature:Oracle Database Full Backup and Point-in-Time Restore Validation On RHEL Servers using Rubrik


  Scenario Outline: [1] Perform Successful Full Backup for Oracle Database
    Given Oracle database <database_name> with version <oracle_version> on <server_ip>
    And the platform is <platform>
    And the OS is <os>
    And the SLA ID is <sla_id>
    When the method to trigger full database backup is called
    Then the method returns status <full_backup_trigger_status>
    When the method to get the full database backup status is called
    Then the method returns full backup status <full_backup_status>
    And the table <table_name> is created in the database <database_name>
    And one row of data is inserted into the table <table_name>
    Examples:
      | server_ip    | platform   | os        | sla_id | database_name | table_name   | oracle_version | full_backup_trigger_status | full_backup_status |
      | 10.81.91.106 | IaaS (AWS) | RHEL 8.10 | valid  | ORCL_8        | test_table_8 | 19.0.0.0       | Backup triggered           | Backup successful  |


  Scenario Outline: [2] Perform Successful Point-in-Time Restore on same server.
    Given Oracle database <database_name> with version <oracle_version> on <server_ip>
    And Database <database_name> with <table_name> was backed up on <server_ip>
    And the platform is <platform>
    And the OS is <os>
    And the PITR restore time is <pitr_restore_time>
    When the method to delete the database is called
    Then the method returns status <db_delete_status>
    When the method to get the database is called
    Then the method returns status <check_db_status>
    When the method to trigger Point-in-Time restore is called with point-in-time <restore_time>
    Then the method returns status <pitr_trigger_status>
    When the method to get the Point-in-Time restore status is called
    Then the method returns restore status <restore_db_status>
    When the method to get the database and get table is called
    Then the method returns status <db_exists_status>
    And the method returns status <table_exists_status> for <table_name>
    Examples:
      | server_ip    | platform   | os        | pitr_restore_time | database_name | table_name   | oracle_version | db_delete_status        | db_exists_status               | table_exists_status               | pitr_trigger_status | restore_time            | restore_db_status  | db_exists_status       | table_exists_status       |
      | 10.81.91.106 | IaaS (AWS) | RHEL 8.10 | valid             | ORCL_8        | test_table_8 | 19.0.0.0       | Database ORCL_8 deleted | Database ORCL_8 does not exist | Table test_table_8 does not exist | Restore triggered   | YYYY-MM-DD 1H:MM:SS UTC | Restore successful | Database ORCL_8 exists | Table test_table_8 exists |


  Scenario Outline: [3] Perform Oracle Backup Failure Scenario
    Given Oracle database <oracle_version> with version <oracle_version> on <server_ip>
    And the platform is <platform>
    And the OS is <os>
    And the SLA ID is <sla_id>
    When the method to trigger full database backup is called
    Then the method returns status <full_backup_trigger_status>
    Examples:
      | server_ip    | platform   | os        | sla_id  | oracle_version | full_backup_trigger_status |
      | 10.81.91.106 | IaaS (AWS) | RHEL 8.10 | invalid | 19.0.0.0       | Backup trigger failed      |


  Scenario Outline: [4] Perform Oracle Point-in-Time Restore Failure Scenario (Outside Backup Range)
    Given Oracle database <oracle_version> with <database_name> and <table_name> was backed up on <server_ip>
    And the platform is <platform>
    And the OS is <os>
    And the PITR restore time is <pitr_restore_time>
    When the method to trigger Point-in-Time restore is called
    Then the method returns status <pitr_trigger_status>
    Examples:
      | server_ip    | platform   | os        | pitr_restore_time | database_name | table_name   | oracle_version | pitr_trigger_status    |
      | 10.81.91.106 | IaaS (AWS) | RHEL 8.10 | invalid           | ORCL_8        | test_table_8 | 19.0.0.0       | Restore trigger failed |
