import React from 'react';

export function UserCard({ name }: { name: string }) {
  return <div className="card">{name}</div>;
}
