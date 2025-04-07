import { Contact, ContactFormData } from '../types/contact';
import { api } from './api';

export const contactService = {
  async getContacts(): Promise<Contact[]> {
    try {
      const response = await api.get('/api/contacts');
      return response.data;
    } catch (error) {
      console.error('Failed to fetch contacts:', error);
      throw new Error('Failed to fetch contacts');
    }
  },

  async createContact(data: ContactFormData): Promise<Contact> {
    try {
      const response = await api.post('/api/contacts', data);
      return response.data;
    } catch (error) {
      console.error('Failed to create contact:', error);
      throw new Error('Failed to create contact');
    }
  },

  async updateContact(id: string, data: ContactFormData): Promise<Contact> {
    try {
      const response = await api.put(`/api/contacts/${id}`, data);
      return response.data;
    } catch (error) {
      console.error('Failed to update contact:', error);
      throw new Error('Failed to update contact');
    }
  },

  async deleteContact(id: string): Promise<void> {
    try {
      await api.delete(`/api/contacts/${id}`);
    } catch (error) {
      console.error('Failed to delete contact:', error);
      throw new Error('Failed to delete contact');
    }
  }
};