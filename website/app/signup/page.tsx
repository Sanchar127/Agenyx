import { AuthPanel } from '@/components/auth/auth-panel';

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; message?: string }>;
}) {
  const { error, message } = await searchParams;

  return <AuthPanel mode='signup' error={error} message={message} />;
}
