import React, { useState, useEffect } from 'react';
import { Contact, ContactFormData } from '../../types/contact';
import { contactService } from '../../services/contactService';
import ContactModal from './ContactModal';

const ContactList: React.FC = () => {
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [selectedContact, setSelectedContact] = useState<Contact | undefined>();
  const [operationLoading, setOperationLoading] = useState(false);

  useEffect(() => {
    loadContacts();
  }, []);

  const loadContacts = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await contactService.getContacts();
      setContacts(data);
    } catch (err: any) {
      const errorMessage = err.response?.data?.error || err.message || 'Failed to load contacts';
      setError(`Error: ${errorMessage}`);
      console.error('Load contacts error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('Are you sure you want to delete this contact?')) return;
    
    try {
      setOperationLoading(true);
      setError(null);
      await contactService.deleteContact(id);
      setContacts(contacts.filter((contact: Contact) => contact.id !== id));
      setError(null);
    } catch (err: any) {
      const errorMessage = err.response?.data?.error || err.message || 'Failed to delete contact';
      setError(`Error: ${errorMessage}`);
      console.error('Delete contact error:', err);
    } finally {
      setOperationLoading(false);
    }
  };

  const handleSave = async (data: ContactFormData) => {
    try {
      setOperationLoading(true);
      setError(null);
      
      if (selectedContact) {
        const updatedContact = await contactService.updateContact(selectedContact.id, data);
        setContacts(contacts.map((c: Contact) => c.id === selectedContact.id ? updatedContact : c));
      } else {
        const newContact = await contactService.createContact(data);
        setContacts([...contacts, newContact]);
      }
      
      setIsModalOpen(false);
      setSelectedContact(undefined);
      setError(null);
    } catch (err: any) {
      const errorMessage = err.response?.data?.error || err.message || 'Failed to save contact';
      setError(`Error: ${errorMessage}`);
      console.error('Save contact error:', err);
      throw new Error(errorMessage);
    } finally {
      setOperationLoading(false);
    }
  };

  const openAddModal = () => {
    setSelectedContact(undefined);
    setIsModalOpen(true);
  };

  const openEditModal = (contact: Contact) => {
    setSelectedContact(contact);
    setIsModalOpen(true);
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="text-gray-500">Loading contacts...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 p-4 rounded-md">
        <div className="flex justify-between items-center">
          <div className="text-red-700">{error}</div>
          <button
            onClick={() => setError(null)}
            className="text-red-700 hover:text-red-900"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-2xl font-bold text-gray-900">Contacts</h2>
        <button
          className="btn-primary"
          onClick={openAddModal}
        >
          Add Contact
        </button>
      </div>

      <div className="bg-white shadow overflow-hidden sm:rounded-md">
        {contacts.length === 0 ? (
          <div className="text-center py-6 text-gray-500">
            No contacts found. Add your first contact!
          </div>
        ) : (
          <ul className="divide-y divide-gray-200">
            {contacts.map((contact: Contact) => (
              <li key={contact.id} className="px-6 py-4 hover:bg-gray-50">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-lg font-medium text-gray-900">
                      {contact.fullName}
                    </h3>
                    {contact.email && (
                      <p className="text-sm text-gray-500">{contact.email}</p>
                    )}
                    {contact.phone && (
                      <p className="text-sm text-gray-500">{contact.phone}</p>
                    )}
                  </div>
                  <div className="flex space-x-4">
                    <button
                      onClick={() => openEditModal(contact)}
                      className="text-indigo-600 hover:text-indigo-900"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDelete(contact.id)}
                      className="text-red-600 hover:text-red-900"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ContactModal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setSelectedContact(undefined);
          setError(null);
        }}
        onSave={handleSave}
        contact={selectedContact}
        loading={operationLoading}
      />
    </div>
  );
};

export default ContactList;