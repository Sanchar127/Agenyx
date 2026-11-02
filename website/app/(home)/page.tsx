import { Hero } from '@/components/marketing/hero';
import { Features } from '@/components/marketing/features';
import { Architecture } from '@/components/marketing/architecture';
import { Cta } from '@/components/marketing/cta';
import { Footer } from '@/components/marketing/footer';

export default function HomePage() {
  return (
    <>
      <Hero />
      <Features />
      <Architecture />
      <Cta />
      <Footer />
    </>
  );
}
