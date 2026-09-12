export type UserRole = 'client' | 'operator' | 'supervisor' | 'admin';

export interface UserProfile {
  id: string;
  role_code: UserRole;
  email: string;
  full_name?: string | null;
  company_name?: string | null;
  inn?: string | null;
  line_code?: string;
  created_at?: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: UserProfile;
}
