import axios from 'axios';
import { Contact, ContactFormData } from '../types/contact';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8191';

export const contactService = {
  async getContacts(): Promise<Contact[]> {
    const response = await axios.get(`${API_URL}/api/contacts`);
    return response.data;
  },

  async createContact(data: ContactFormData): Promise<Contact> {
    const response = await axios.post(`${API_URL}/api/contacts`, data);
    return response.data;
  },

  async updateContact(id: string, data: ContactFormData): Promise<Contact> {
    const response = await axios.put(`${API_URL}/api/contacts/${id}`, data);
    return response.data;
  },

  async deleteContact(id: string): Promise<void> {
    await axios.delete(`${API_URL}/api/contacts/${id}`);
  }
};