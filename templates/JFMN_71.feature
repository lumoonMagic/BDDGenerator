Feature: MSSQL Full Database Backup & Restore on windows server using Rubrik with Always On Availability Groups (AOAG) enabled

  Scenario Outline: [1] Perform Successful MSSQL Backup
    Given MSSQL database version is <mssql_version>
    And Database is <database_name> added to AOAG with primary replica on <primary_ip> and secondary replica on <secondary_ip>
    And Table <table_name> is created on <primary_ip>
    And the platform is <platform>
    And the OS is <os>
    And the sla id is <sla_id>
    And the table <table_name> is inserted with first row of data on <primary_ip> before failing over the primary replica
    When the method to trigger full database backup which includes Transaction Logs is called
    Then the method returns trigger full backup status <trigger_backup_status>
    When the method to get the full backup status is called
    Then the method returns full backup status <backup_status>
    And fail over the primary replica to secondary replica
    Then the table <table_name> is inserted with second row of data on <secondary_ip> after failing over the primary replica
    Examples:
      | primary_ip   | secondary_ip  | platform   | os           | sla_id | database_name | table_name          | mssql_version | trigger_backup_status | backup_status          |
      | 10.81.203.37 | 10.81.203.100 | IaaS (AWS) | Windows 2022 | valid  | SDLC_Failover | SDLC_Failover_Table | 2022          | Full backup triggered | Full backup successful |

  Scenario Outline: [2] Perform Successful MSSQL Restore
    Given MSSQL Database <database_name> with <mssql_version> and <table_name> was backed up on <primary_ip>
    And secondary replica is now primary replica on <secondary_ip>
    And the platform is <platform>
    And the OS is <os>
    And the snapshot id is <snapshot_id>
    And fail back the secondary replica to original primary replica on <primary_ip>
    When the method to trigger full database restore is called on <primary_ip>
    Then the method returns trigger full restore status <trigger_restore_status>
    When the method to get database full restore status is called
    Then the method returns database full restore status <restore_status>
    When the method to get the database <database_name> and get table <table_name> with table data is called on <primary_ip>
    Then the method returns database exists status <db_exists_status>
    And the method returns table exists status <table_exists>
    And the method returns table data status <table_data_status> to match the inserted data
    Examples:
      | primary_ip   | secondary_ip  | platform  | os           | snapshot_id | database_name | table_name          | mssql_version | trigger_restore_status | restore_status     | db_exists_status              | table_exists                     | table_data_status  |
      | 10.81.203.37 | 10.81.203.100 | IaaS(AWS) | Windows 2022 | valid       | SDLC_Failover | SDLC_Failover_Table | 2022          | Restore triggered      | Restore successful | Database SDLC_Failover exists | Table SDLC_Failover_Table exists | Table data matched |

  Scenario Outline: [3] Perform MSSQL Backup Failure Scenario
    Given MSSQL database version is <mssql_version>
    And Database is <database_name> added to AOAG with primary replica on <primary_ip> and secondary replica on <secondary_ip>
    And Table <table_name> is created on <primary_ip>
    And the platform is <platform>
    And the OS is <os>
    And the sla id is <sla_id>
    When the method to trigger full database backup which includes Transaction Logs is called
    Then the method returns trigger full backup status <trigger_backup_status>
    Examples:
      | primary_ip   | secondary_ip  | platform   | os           | sla_id  | database_name | table_name          | mssql_version | trigger_backup_status      |
      | 10.81.203.37 | 10.81.203.100 | IaaS (AWS) | Windows 2022 | invalid | SDLC_Failover | SDLC_Failover_Table | 2022          | Full backup trigger failed |


  Scenario Outline: [4] Perform MSSQL Restore Failure Scenario
    Given MSSQL Database <database_name> with <mssql_version> and <table_name> was backed up on <primary_ip>
    And secondary replica is now primary replica on <secondary_ip>
    And the platform is <platform>
    And the OS is <os>
    And the snapshot id is <snapshot_id>
    When the method to trigger full database restore is called on <primary_ip>
    Then the method returns trigger full restore status <trigger_restore_status>
    Examples:
      | primary_ip   | secondary_ip  | platform  | os           | snapshot_id | database_name | table_name          | mssql_version | trigger_restore_status |
      | 10.81.203.37 | 10.81.203.100 | IaaS(AWS) | Windows 2022 | invalid     | SDLC_Failover | SDLC_Failover_Table | 2022          | Restore trigger failed |
