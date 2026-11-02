import { PlaygroundShell } from '@/components/playground/playground-shell';

export default function PlaygroundLayout({ children }: LayoutProps<'/playground'>) {
  return <PlaygroundShell>{children}</PlaygroundShell>;
}
