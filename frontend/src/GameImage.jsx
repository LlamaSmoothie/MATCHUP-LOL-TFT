import React from 'react';
import { fallbackImage } from './assets.js';

export default function GameImage({ loading = 'lazy', ...props }) {
  return <img {...props} loading={loading} decoding="async" onError={fallbackImage} />;
}
