import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';

import Home from '@/app/page';

describe('Home', () => {
  it('links each showcase category using its catalog category value', () => {
    render(<Home />);

    expect(screen.getByRole('link', { name: /Бытовая техника/i })).toHaveAttribute(
      'href',
      '/catalog?category=%D0%91%D1%8B%D1%82%D0%BE%D0%B2%D0%B0%D1%8F%20%D1%82%D0%B5%D1%85%D0%BD%D0%B8%D0%BA%D0%B0',
    );
    expect(screen.getByRole('link', { name: /Электроника/i })).toHaveAttribute(
      'href',
      '/catalog?category=%D0%AD%D0%BB%D0%B5%D0%BA%D1%82%D1%80%D0%BE%D0%BD%D0%B8%D0%BA%D0%B0',
    );
  });
});
