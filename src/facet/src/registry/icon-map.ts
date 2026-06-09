/**
 * icon-map.ts
 *
 * Maps the string icon keys used in presentation.json files to React-icons
 * components from `react-icons/fi` (Feather Icons).
 *
 * To add a new icon:
 *   1. Import it from 'react-icons/fi'
 *   2. Add the mapping below
 *   3. Use the key string in any `presentation.json` → `"icon": "<key>"`
 */
import type { IconType } from 'react-icons';
import {
  FiArchive,
  FiCheckCircle,
  FiCode,
  FiCpu,
  FiDatabase,
  FiEye,
  FiFile,
  FiFileText,
  FiImage,
  FiKey,
  FiLink,
  FiLock,
  FiMessageCircle,
  FiMonitor,
  FiMusic,
  FiPackage,
  FiServer,
  FiShield,
  FiUser,
  FiUsers,
  FiVideo,
  FiZap,
} from 'react-icons/fi';

export const ICON_MAP: Record<string, IconType> = {
  'archive': FiArchive,
  'message-circle': FiMessageCircle,
  'check-circle': FiCheckCircle,
  'code': FiCode,
  'eye': FiEye,
  'cpu': FiCpu,
  'database': FiDatabase,
  'file': FiFile,
  'file-text': FiFileText,
  'image': FiImage,
  'key': FiKey,
  'link': FiLink,
  'lock': FiLock,
  'monitor': FiMonitor,
  'music': FiMusic,
  'package': FiPackage,
  'server': FiServer,
  'shield': FiShield,
  'user': FiUser,
  'users': FiUsers,
  'video': FiVideo,
  'zap': FiZap,
};

/** Returns the IconType for a given icon key, falling back to FiFile. */
export function resolveIcon(key: string | null | undefined): IconType {
  if (!key) return FiFile;
  return ICON_MAP[key] ?? FiFile;
}
