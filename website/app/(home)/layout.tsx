import { HomeLayout as HomeLayoutComponent } from 'fumadocs-ui/layouts/home';
import { SiteHeader } from '@/components/layout/site-header';
import { baseOptions } from '@/lib/layout.shared';

export default function Home({ children }: LayoutProps<'/'>) {
  const options = baseOptions();

  return (
    <HomeLayoutComponent
      nav={options.nav}
      githubUrl={options.githubUrl}
      links={options.links}
      slots={{ header: SiteHeader }}
    >
      {children}
    </HomeLayoutComponent>
  );
}
