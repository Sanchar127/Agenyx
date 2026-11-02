import { AuthPanel } from '@/components/auth/auth-panel';

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;

  return <AuthPanel mode='signup' error={error} />;
}
