'use client';

import { useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { LoaderCircle } from 'lucide-react';

import { ApiError, authApi } from '@/lib/api/client';

interface CredentialsFormProps {
  mode: 'login' | 'signup';
}

export function CredentialsForm({ mode }: CredentialsFormProps) {
  const router = useRouter();
  const isLogin = mode === 'login';

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);

    const trimmedEmail = email.trim();

    if (!trimmedEmail || !password) {
      setError('Please enter both an email and a password.');
      return;
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      setError('Please enter a valid email address.');
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }

    setIsSubmitting(true);

    try {
      await (isLogin
        ? authApi.loginWithEmail
        : authApi.signupWithEmail)(trimmedEmail, password);

      router.push('/playground');
    } catch (caught) {
      const message =
        caught instanceof ApiError
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : 'Authentication failed. Please try again.';

      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className='mt-6 space-y-4' noValidate>
      <div>
        <label
          htmlFor='auth-email'
          className='block text-sm font-medium text-fd-foreground'
        >
          Email
        </label>
        <input
          id='auth-email'
          name='email'
          type='email'
          autoComplete='email'
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder='you@company.com'
          className='mt-1.5 h-10 w-full rounded-md border border-fd-border bg-fd-background px-3 text-sm text-fd-foreground placeholder:text-fd-muted-foreground focus:outline-none focus:ring-2 focus:ring-emerald-500/40'
        />
      </div>

      <div>
        <label
          htmlFor='auth-password'
          className='block text-sm font-medium text-fd-foreground'
        >
          Password
        </label>
        <input
          id='auth-password'
          name='password'
          type='password'
          autoComplete={isLogin ? 'current-password' : 'new-password'}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder='••••••••'
          className='mt-1.5 h-10 w-full rounded-md border border-fd-border bg-fd-background px-3 text-sm text-fd-foreground placeholder:text-fd-muted-foreground focus:outline-none focus:ring-2 focus:ring-emerald-500/40'
        />
      </div>

      {error ? (
        <div
          role='alert'
          className='rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400'
        >
          {error}
        </div>
      ) : null}

      <button
        type='submit'
        disabled={isSubmitting}
        className='inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-emerald-600 px-6 text-sm font-semibold text-white transition-colors hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50'
      >
        {isSubmitting ? (
          <>
            <LoaderCircle className='h-4 w-4 animate-spin' />
            Please wait…
          </>
        ) : isLogin ? (
          'Sign in'
        ) : (
          'Create account'
        )}
      </button>
    </form>
  );
}
