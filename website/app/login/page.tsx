import { AuthPanel } from '@/components/auth/auth-panel';

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;

  return <AuthPanel mode='login' error={error} />;
}
