import os
import pyodbc
import configparser
from models.utility import Utility
from datetime import datetime
import time


class MSSQLConnection:
    def __init__(self):
        """

        """
        self.current_working_directory = os.getcwd()
        self.config_file_path = os.path.join(self.current_working_directory, "config")
        self.config_file = os.path.join(self.config_file_path, "main_config.ini")
        self.config = configparser.ConfigParser()
        self.config.read(self.config_file)

        if not os.path.exists(self.config_file):
            raise FileNotFoundError(f"Config file not found: {self.config_file}")

        self.username = self.config["mssql_connection_details"]["username"]
        self.password = Utility.decode(self.config["mssql_connection_details"]["password"])
        self.driver = self.config["mssql_connection_details"]["driver"]

    def connect(self, server_ip, database_name):
        try:
            print(f"Attempting to connect to SQL server {server_ip} with {database_name}")
            connection = pyodbc.connect(
                f"DRIVER={self.driver};"
                f"SERVER={server_ip};"
                f"DATABASE={database_name};"
                f"UID={self.username};"
                f"PWD={self.password};"
                f"TrustServerCertificate=yes;",
                autocommit=True
            )
            print(f"Successfully connected to SQL server {server_ip}")
            return connection
        except pyodbc.Error as error:
            msg = f"Error connecting to SQL server {server_ip}\n{str(error)}"
            raise pyodbc.Error(msg)

    def switch_database(self, server_ip, database_name):
        connection = None
        cursor = None
        try:
            # Connect to master (or default DB)
            connection = self.connect(server_ip, database_name)
            cursor = connection.cursor()

            # Switch to the given database
            cursor.execute(f"USE [{database_name}]")
            print(f"Switched to database: {database_name}")
            return connection  # return connection now pointing to new DB

        except Exception as error:
            return f"Failed to switch database: {str(error)}"

        finally:
            if cursor:
                cursor.close()
            if connection: connection.close()

    def create_database(self, server_ip, database_name):
        cursor = None
        connection = None
        try:
            connection = self.connect(server_ip, "master")
            connection.autocommit = True
            cursor = connection.cursor()

            sql = f"SELECT COUNT(*) FROM sys.databases WHERE name = '{database_name}'"
            cursor.execute(sql)
            exists = cursor.fetchone()[0] > 0

            if exists:
                return f"Database {database_name} already exists"

            cursor.execute(f"CREATE DATABASE [{database_name}]")
            connection.commit()
            return f"Database {database_name} created"

        except Exception as error:
            msg = f"Database {database_name} creation failed on {server_ip}\nError: {str(error)}"
            print(msg)
            return "Database creation failed"
        finally:
            if cursor: cursor.close()
            if connection: connection.close()

    def get_database(self, server_ip, database_name):
        cursor = None
        connection = None
        try:
            connection = self.connect(server_ip, "master")
            cursor = connection.cursor()

            sql = f"SELECT COUNT(*) FROM sys.databases WHERE name = '{database_name}'"

            cursor.execute(sql)
            result = cursor.fetchone()
            print(result)
            exists = result[0] > 0

            if exists:
                return f"Database {database_name} exists"
            else:
                return f"Database {database_name} does not exist"

        except Exception as error:
            msg = f"Failed to get database {database_name} on {server_ip}.\nError: {str(error)}"
            print(msg)
            return f"Database {database_name} does not exist"
        finally:
            if cursor: cursor.close()
            if connection: connection.close()


    def delete_database(self, server_ip, database_name):
        cursor = None
        connection = None
        try:
            connection = self.connect(server_ip, "master")
            cursor = connection.cursor()

            # Check if database exists
            cursor.execute(f"SELECT COUNT(*) FROM sys.databases WHERE name = '{database_name}'")
            exists = cursor.fetchone()[0] > 0

            if not exists:
                return f"Database {database_name} does not exist"

            # Force single-user mode and drop
            cursor.execute(f"ALTER DATABASE [{database_name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            cursor.execute(f"DROP DATABASE [{database_name}]")
            connection.commit()

            return f"Database {database_name} deleted"

        except Exception as error:
            msg = f"Database {database_name} deletion failed on {server_ip}\nError: {error}"
            print(msg)
            return "Database deletion failed"
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def get_current_timestamp(self):
        return datetime.now()

    def create_table(self, server_ip, database_name, table_name):
        cursor = None
        connection = None
        try:
            connection = self.connect(server_ip, database_name)
            cursor = connection.cursor()

            # Check if table already exists
            sql = f"SELECT * FROM [{database_name}].INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='{table_name}' AND TABLE_SCHEMA='dbo'"
            cursor.execute(sql)
            if cursor.fetchone():
                return f"Table {table_name} already exists"

            create_sql = f"""
            CREATE TABLE [{database_name}].[dbo].[{table_name}] (
                ID INT IDENTITY(1,1) PRIMARY KEY,
                test_db NVARCHAR(255),
                test_backup NVARCHAR(255),
                record_timestamp NVARCHAR(50)
            )
            """
            cursor.execute(create_sql)
            connection.commit()
            return f"Table {table_name} created"

        except Exception as error:
            msg = f"Table {table_name} creation failed in {database_name} on {server_ip}\nError: {str(error)}"
            print(msg)
            return "Table creation failed"
        finally:
            if cursor: cursor.close()
            if connection: connection.close()

    def get_table(self, server_ip, database_name, table_name):
        cursor = None
        connection = None
        try:
            connection = self.connect(server_ip, database_name)
            cursor = connection.cursor()
            # List all tables in the database
            sql = f"SELECT TABLE_NAME FROM [{database_name}].INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' AND TABLE_SCHEMA='dbo'"
            cursor.execute(sql)
            tables = [row[0] for row in cursor.fetchall()]
            print(f"Tables in {database_name}: {tables}")
            if table_name in tables:
                return f"Table {table_name} exists"
            else:
                return f"Table {table_name} does not exist"
        except Exception as error:
            print(f"Error in get_table: {error}")
            return f"Table {table_name} does not exist"
        finally:
            if cursor: cursor.close()
            if connection: connection.close()

    def insert_test_data(self, server_ip, database_name, table_name, backup_type):
        cursor = None
        connection = None
        try:
            connection = self.connect(server_ip, database_name)
            cursor = connection.cursor()
            current_timestamp = self.get_current_timestamp()
            insert_sql = f"""
            INSERT INTO [{database_name}].[dbo].[{table_name}] (test_db, test_backup, record_timestamp) VALUES 
            ('{database_name}', '{backup_type}', '{current_timestamp}')
            """
            cursor.execute(insert_sql)
            connection.commit()
            print(f"Inserted test_db {database_name}, backup type {backup_type}, record_timestamp {current_timestamp} into {table_name}")
            return "Test data inserted successfully"
        except Exception as error:
            return f"Test data insertion failed: {str(error)}"
        finally:
            if cursor: cursor.close()
            if connection: connection.close()

    def print_all_inserted(self, server_ip, database_name, table_name):
        try:
            conn = self.connect(server_ip, database_name)
            cursor = conn.cursor()
            # cursor.execute(f"USE [{database_name}]")

            cursor.execute(f"SELECT * FROM [dbo].[{table_name}] ORDER BY ID DESC")
            rows = cursor.fetchall()

            if not rows:
                print("No records found.")
                return "No records found."

            return rows

        except Exception as e:
            if "Invalid object name" in str(e):
                msg = f"Table {table_name} does not exist in database {database_name} on server {server_ip}."
                print(msg)
            else:
                msg = f"Error fetching data from table {table_name} in database {database_name} on server {server_ip}.\nError: {str(e)}"
                print(msg)
            return msg
        finally:
            cursor.close()
            conn.close()

    def delete_table(self, server_ip, database_name, table_name):
        cursor = None
        connection = None
        try:


            table_exists = self.get_table(server_ip, database_name, table_name)
            if "does not exist" in table_exists:
                return f"Table {table_name} does not exist"

            connection = self.connect(server_ip, database_name)
            cursor = connection.cursor()

            # Drop the table
            cursor.execute(f"DROP TABLE {database_name}.[dbo].{table_name}")
            connection.commit()

            return f"Table {table_name} deleted"

        except Exception as error:
            return f"Table deletion failed in {database_name} on {server_ip}: {error}"
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def poll_for_table(self, server_ip, database_name, table_name):
        """
        Polls for the existence of a table with retries at 30s, 60s, and 90s intervals.
        Returns success message if found, error if not found after all retries.
        """
        try:
            intervals = [30, 60, 90]
            for wait_time in intervals:
                result = self.get_table(server_ip, database_name, table_name)
                if result and "exists" in result and "does not exist" not in result:
                    return f"Table {table_name} exists"
                print(f"Table {table_name} not found. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            # Final attempt after all retries
            result = self.get_table(server_ip, database_name, table_name)
            if result and "exists" in result and "does not exist" not in result:
                return f"Table {table_name} exists"
            return f"Table {table_name} does not exist"
        except Exception as e:
            return f"Error polling for table {table_name}: {str(e)}"

    def describe_table(self, server_ip, database_name, table_name):
        cursor = None
        connection = None
        try:
            connection = self.connect(server_ip, database_name)
            cursor = connection.cursor()
            sql = f"""
                SELECT COLUMN_NAME, DATA_TYPE
                FROM [{database_name}].INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = '{table_name}' AND TABLE_SCHEMA = 'dbo'
            """
            cursor.execute(sql)
            columns = cursor.fetchall()
            if not columns:
                return f"Table {table_name} does not exist or has no columns."
            result = [f"{col[0]}: {col[1]}" for col in columns]
            return f"Table {table_name} columns:\n" + "\n".join(result)
        except Exception as error:
            return f"Error describing table {table_name}: {error}"
        finally:
            if cursor: cursor.close()
            if connection: connection.close()

    def execute_query(self, server_ip, database_name, query, params=None):
        """
        Executes a given SQL query on the specified server and database.
        Args:
            server_ip (str): SQL Server IP address
            database_name (str): Database name
            query (str): SQL query to execute
            params (tuple, optional): Parameters for parameterized queries
        Returns:
            dict: Contains 'rows' (if any), 'rowcount', and 'message'.
        """
        cursor = None
        connection = None
        try:
            connection = self.connect(server_ip, database_name)
            cursor = connection.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            rows = None
            try:
                rows = cursor.fetchall()
            except Exception:
                pass  # Not all queries return rows
            rowcount = cursor.rowcount
            connection.commit()
            return {
                'rows': rows,
                'rowcount': rowcount,
                'message': 'Query executed successfully'
            }
        except Exception as error:
            return {
                'rows': None,
                'rowcount': -1,
                'message': f'Error executing query: {error}'
            }
        finally:
            if cursor: cursor.close()
            if connection: connection.close()


    def poll_for_database(self, server_ip, database_name):
        """
        Polls for the existence of a database with retries at 30s, 60s, and 90s intervals.
        Returns success message if found, error if not found after all retries.
        """
        try:
            intervals = [30, 60, 90]
            for wait_time in intervals:
                result = self.get_database(server_ip, database_name)
                if result and "exists" in result and "does not exist" not in result:
                    return f"Database {database_name} exists"
                print(f"Database {database_name} not found. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            # Final attempt after all retries
            result = self.get_database(server_ip, database_name)
            if result and "exists" in result and "does not exist" not in result:
                return f"Database {database_name} exists"
            return f"Database {database_name} does not exist"
        except Exception as e:
            return f"Error polling for database {database_name}: {str(e)}"