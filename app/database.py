import sqlite3

import os

DATABASE_FILE = os.path.join(os.getcwd(), "contacts.db")

def init_db():
    """Initialize the SQLite database and create the contacts table if it doesn't exist."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contacts (
            id TEXT PRIMARY KEY,
            name TEXT,
            email TEXT,
            phone TEXT,
            org TEXT,
            url TEXT,
            birthday TEXT,
            note TEXT,
            photo BLOB,
            address TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_contact(contact):
    """Add a new contact to the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO contacts (id, name, email, phone, org, url, birthday, note, photo, address)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        contact.get('id'),
        contact.get('name'),
        contact.get('email'),
        contact.get('phone'),
        contact.get('org'),
        contact.get('url'),
        contact.get('birthday'),
        contact.get('note'),
        contact.get('photo'),
        contact.get('address')
    ))
    conn.commit()
    conn.close()

def get_all_contacts():
    """Retrieve all contacts from the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM contacts')
    contacts = cursor.fetchall()
    conn.close()
    return contacts

def update_contact(contact_id, updated_contact):
    """Update an existing contact in the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE contacts
        SET name = ?, email = ?, phone = ?, org = ?, url = ?, birthday = ?, note = ?, photo = ?, address = ?
        WHERE id = ?
    ''', (
        updated_contact.get('name'),
        updated_contact.get('email'),
        updated_contact.get('phone'),
        updated_contact.get('org'),
        updated_contact.get('url'),
        updated_contact.get('birthday'),
        updated_contact.get('note'),
        updated_contact.get('photo'),
        updated_contact.get('address'),
        contact_id
    ))
    conn.commit()
    conn.close()

def delete_contact(contact_id):
    """Delete a contact from the database."""
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM contacts WHERE id = ?', (contact_id,))
    conn.commit()
    conn.close()