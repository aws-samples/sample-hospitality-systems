import React from 'react';
import Header from './Header';
import Footer from './Footer';

interface PublicLayoutProps {
  children: React.ReactNode;
  transparentHeader?: boolean;
}

const PublicLayout: React.FC<PublicLayoutProps> = ({
  children,
  transparentHeader = false,
}) => {
  return (
    <div className="flex min-h-screen flex-col">
      <Header transparent={transparentHeader} />
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  );
};

export default PublicLayout;
