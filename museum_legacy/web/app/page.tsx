'use client';

import { useEffect, useState } from 'react';

type PlatformEntry = {
  platform: string;
  rent?: { price: number | null };
  buy?: { price: number | null };
  url: string;
};

type Title = {
  id: string;
  title: string;
  poster?: string;
  year?: number;
  genres: string[];
  availabilityDate: string;
  platforms: PlatformEntry[];
};

export default function Page() {
  const [items, setItems] = useState<Title[]>([]);

  useEffect(() => {
    fetch('/new-releases.json', { cache: 'no-store' })
      .then(res => res.json())
      .then(data => setItems(data))
      .catch(console.error);
  }, []);

  return (
    <main className="p-6 bg-black text-white min-h-screen">
      <h1 className="text-2xl font-bold mb-4">New Arrivals</h1>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4">
        {items.map(movie => (
          <div key={movie.id} className="bg-gray-900 rounded-lg overflow-hidden">
            <img
              src={movie.poster || 'https://placehold.co/200x300?text=No+Image'}
              alt={movie.title}
              className="w-full aspect-[2/3] object-cover"
            />
            <div className="p-2">
              <h2 className="text-sm font-semibold">{movie.title}</h2>
              <p className="text-xs text-gray-400">{movie.year || ''}</p>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
