export interface Contact {
  id: string;
  fullName: string;
  email?: string;
  phone?: string;
  organization?: string;
  title?: string;
  notes?: string;
  lastModified: string;
}

export interface ContactFormData {
  fullName: string;
  email: string;
  phone: string;
  organization: string;
  title: string;
  notes: string;
}