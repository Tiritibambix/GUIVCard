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
  email?: string;
  phone?: string;
  organization?: string;
  title?: string;
  notes?: string;
}

// Type pour la validation des champs requis
export interface ContactValidation {
  fullName: boolean;
  email: boolean;
  phone: boolean;
  organization: boolean;
  title: boolean;
  notes: boolean;
}