import { AuthPanel } from '@/components/auth/auth-panel';

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; message?: string }>;
}) {
  const { error, message } = await searchParams;

  return <AuthPanel mode='login' error={error} message={message} />;
}
