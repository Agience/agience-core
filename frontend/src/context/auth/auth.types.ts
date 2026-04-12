// src/api/types/auth.ts
export interface User {
  id: string;
  email: string;
  name: string;
  picture: string;
  roles?: string[];
  oidc_provider?: string;
  has_password?: boolean;
  platform_user_id?: string;
}
