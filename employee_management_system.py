"""
Employee Management System
--------------------------
Console application (Python + MySQL) to manage employee records.

Features : Add, Display, Update, Promote (salary increment), Remove, Search
Design   : OOP (Employee model, Database, EmployeeRepository, App),
           loop-based menu, input validation, error handling,
           parameterized SQL queries, credentials via environment variables.

Setup
-----
1. Install the driver:   pip install mysql-connector-python
2. Create the database/table (run once in MySQL):

       CREATE DATABASE IF NOT EXISTS employee;
       USE employee;
       CREATE TABLE IF NOT EXISTS empdata (
           Id        VARCHAR(20)  PRIMARY KEY,
           Name      VARCHAR(100) NOT NULL,
           Email_Id  VARCHAR(100) NOT NULL,
           Phone_no  VARCHAR(15)  NOT NULL,
           Address   VARCHAR(255),
           Post      VARCHAR(100),
           Salary    DECIMAL(12, 2) NOT NULL
       );

3. (Optional) set environment variables. Defaults are shown in brackets:
       DB_HOST [localhost]   DB_USER [root]
       DB_PASSWORD [empty]   DB_NAME [employee]
"""

import os
import re
from dataclasses import dataclass
from typing import Callable, List, Optional

import mysql.connector
from mysql.connector import Error

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PHONE_REGEX = re.compile(r"^(0|91)?[7-9][0-9]{9}$")


# --------------------------------------------------------------------------- #
# Model
# --------------------------------------------------------------------------- #
@dataclass
class Employee:
    emp_id: str
    name: str
    email: str
    phone: str
    address: str
    post: str
    salary: float

    def display(self) -> None:
        print(f"Employee Id       : {self.emp_id}")
        print(f"Employee Name     : {self.name}")
        print(f"Employee Email Id : {self.email}")
        print(f"Employee Phone No.: {self.phone}")
        print(f"Employee Address  : {self.address}")
        print(f"Employee Post     : {self.post}")
        print(f"Employee Salary   : {self.salary:,.2f}")
        print("-" * 40)


# --------------------------------------------------------------------------- #
# Database connection
# --------------------------------------------------------------------------- #
class Database:
    """Owns the MySQL connection and runs queries safely."""

    def __init__(self) -> None:
        self.connection = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "employee"),
        )

    def fetch_all(self, sql: str, params: tuple = ()) -> list:
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, params)
            return cursor.fetchall()
        finally:
            cursor.close()

    def fetch_one(self, sql: str, params: tuple = ()):
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, params)
            return cursor.fetchone()
        finally:
            cursor.close()

    def execute(self, sql: str, params: tuple = ()) -> int:
        """Run INSERT/UPDATE/DELETE, commit, and return affected row count.
        Rolls back if anything goes wrong."""
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, params)
            self.connection.commit()
            return cursor.rowcount
        except Error:
            self.connection.rollback()
            raise
        finally:
            cursor.close()

    def close(self) -> None:
        if self.connection.is_connected():
            self.connection.close()


# --------------------------------------------------------------------------- #
# Data access layer
# --------------------------------------------------------------------------- #
class EmployeeRepository:
    """All SQL lives here, so the UI code never touches queries."""

    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _to_employee(row: tuple) -> Employee:
        return Employee(
            emp_id=str(row[0]),
            name=row[1],
            email=row[2],
            phone=row[3],
            address=row[4] or "",
            post=row[5] or "",
            salary=float(row[6]),
        )

    def id_exists(self, emp_id: str) -> bool:
        row = self.db.fetch_one("SELECT 1 FROM empdata WHERE Id = %s", (emp_id,))
        return row is not None

    def name_exists(self, name: str) -> bool:
        row = self.db.fetch_one("SELECT 1 FROM empdata WHERE Name = %s", (name,))
        return row is not None

    def add(self, emp: Employee) -> None:
        sql = "INSERT INTO empdata VALUES (%s, %s, %s, %s, %s, %s, %s)"
        self.db.execute(
            sql,
            (emp.emp_id, emp.name, emp.email, emp.phone,
             emp.address, emp.post, emp.salary),
        )

    def get_all(self) -> List[Employee]:
        rows = self.db.fetch_all("SELECT * FROM empdata ORDER BY Id")
        return [self._to_employee(r) for r in rows]

    def get_by_id(self, emp_id: str) -> Optional[Employee]:
        row = self.db.fetch_one("SELECT * FROM empdata WHERE Id = %s", (emp_id,))
        return self._to_employee(row) if row else None

    def update_contact(self, emp_id: str, email: str, phone: str, address: str) -> None:
        sql = ("UPDATE empdata SET Email_Id = %s, Phone_no = %s, Address = %s "
               "WHERE Id = %s")
        self.db.execute(sql, (email, phone, address, emp_id))

    def increase_salary(self, emp_id: str, amount: float) -> None:
        # Done in a single SQL statement: no read-then-write race condition.
        sql = "UPDATE empdata SET Salary = Salary + %s WHERE Id = %s"
        self.db.execute(sql, (amount, emp_id))

    def delete(self, emp_id: str) -> None:
        self.db.execute("DELETE FROM empdata WHERE Id = %s", (emp_id,))


# --------------------------------------------------------------------------- #
# Console UI
# --------------------------------------------------------------------------- #
class EmployeeApp:
    def __init__(self, repo: EmployeeRepository) -> None:
        self.repo = repo
        self.actions = {
            "1": ("Add Employee", self.add_employee),
            "2": ("Display Employee Records", self.display_employees),
            "3": ("Update Employee Record", self.update_employee),
            "4": ("Promote Employee (Increase Salary)", self.promote_employee),
            "5": ("Remove Employee Record", self.remove_employee),
            "6": ("Search Employee Record", self.search_employee),
            "7": ("Exit", None),
        }

    # ---------- input helpers ---------- #
    @staticmethod
    def _clear_screen() -> None:
        os.system("cls" if os.name == "nt" else "clear")

    @staticmethod
    def _pause() -> None:
        input("\nPress Enter to continue...")

    @staticmethod
    def _ask(prompt: str,
             validator: Callable[[str], bool] = lambda s: bool(s),
             error: str = "Input cannot be empty.") -> str:
        """Keep asking until the validator accepts the value."""
        while True:
            value = input(prompt).strip()
            if validator(value):
                return value
            print(f"  ! {error}")

    @staticmethod
    def _ask_positive_number(prompt: str) -> float:
        while True:
            raw = input(prompt).strip()
            try:
                number = float(raw)
                if number > 0:
                    return number
                print("  ! Enter a number greater than 0.")
            except ValueError:
                print("  ! Please enter a valid number.")

    def _ask_existing_id(self) -> Optional[str]:
        """Ask for an ID and make sure it exists. Returns None if not found."""
        emp_id = self._ask("Enter Employee Id: ")
        if not self.repo.id_exists(emp_id):
            print("Employee record does not exist.")
            return None
        return emp_id

    # ---------- menu actions ---------- #
    def add_employee(self) -> None:
        print("\n--- Add Employee Record ---")
        emp_id = self._ask(
            "Enter Employee Id: ",
            lambda v: bool(v) and not self.repo.id_exists(v),
            "ID is empty or already exists.",
        )
        name = self._ask(
            "Enter Employee Name: ",
            lambda v: bool(v) and not self.repo.name_exists(v),
            "Name is empty or already exists.",
        )
        email = self._ask("Enter Employee Email ID: ",
                          lambda v: bool(EMAIL_REGEX.match(v)), "Invalid email.")
        phone = self._ask("Enter Employee Phone No.: ",
                          lambda v: bool(PHONE_REGEX.match(v)), "Invalid phone number.")
        address = self._ask("Enter Employee Address: ")
        post = self._ask("Enter Employee Post: ")
        salary = self._ask_positive_number("Enter Employee Salary: ")

        self.repo.add(Employee(emp_id, name, email, phone, address, post, salary))
        print("Successfully added employee record.")

    def display_employees(self) -> None:
        print("\n--- All Employee Records ---")
        employees = self.repo.get_all()
        if not employees:
            print("No records found.")
            return
        for emp in employees:
            emp.display()
        print(f"Total employees: {len(employees)}")

    def update_employee(self) -> None:
        print("\n--- Update Employee Record ---")
        emp_id = self._ask_existing_id()
        if emp_id is None:
            return
        email = self._ask("Enter new Email ID: ",
                          lambda v: bool(EMAIL_REGEX.match(v)), "Invalid email.")
        phone = self._ask("Enter new Phone No.: ",
                          lambda v: bool(PHONE_REGEX.match(v)), "Invalid phone number.")
        address = self._ask("Enter new Address: ")

        self.repo.update_contact(emp_id, email, phone, address)
        print("Employee record updated.")

    def promote_employee(self) -> None:
        print("\n--- Promote Employee ---")
        emp_id = self._ask_existing_id()
        if emp_id is None:
            return
        amount = self._ask_positive_number("Enter salary increase amount: ")

        self.repo.increase_salary(emp_id, amount)
        print("Employee promoted. Salary updated.")

    def remove_employee(self) -> None:
        print("\n--- Remove Employee Record ---")
        emp_id = self._ask_existing_id()
        if emp_id is None:
            return
        confirm = input("Are you sure you want to delete this record? (y/n): ")
        if confirm.strip().lower() == "y":
            self.repo.delete(emp_id)
            print("Employee removed.")
        else:
            print("Deletion cancelled.")

    def search_employee(self) -> None:
        print("\n--- Search Employee Record ---")
        emp_id = self._ask("Enter Employee Id: ")
        emp = self.repo.get_by_id(emp_id)
        if emp is None:
            print("Employee record does not exist.")
        else:
            emp.display()

    # ---------- main loop ---------- #
    def _show_menu(self) -> None:
        self._clear_screen()
        print("=" * 44)
        print("     EMPLOYEE MANAGEMENT SYSTEM")
        print("=" * 44)
        for key, (label, _) in self.actions.items():
            print(f"{key}. {label}")
        print()

    def run(self) -> None:
        while True:
            self._show_menu()
            choice = input("Enter your choice [1-7]: ").strip()

            if choice not in self.actions:
                print("Invalid choice. Please enter a number from 1 to 7.")
                self._pause()
                continue

            if choice == "7":
                print("Have a nice day!")
                break

            _, action = self.actions[choice]
            try:
                action()
            except Error as db_error:
                print(f"Database error: {db_error}")
            self._pause()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> None:
    try:
        db = Database()
    except Error as err:
        print(f"Could not connect to the database: {err}")
        return

    try:
        EmployeeApp(EmployeeRepository(db)).run()
    except (KeyboardInterrupt, EOFError):
        print("\nExiting...")
    finally:
        db.close()


if __name__ == "__main__":
    main()
