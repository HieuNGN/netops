import { useQuery } from '@tanstack/react-query';
import { devicesApi } from '../api/endpoints';
import type { Device } from '../api/endpoints';

export function useDevice(deviceId: string | undefined) {
  return useQuery<Device>({
    queryKey: ['device', deviceId],
    queryFn: async () => {
      if (!deviceId) throw new Error('Device ID required');
      const res = await devicesApi.get(deviceId);
      return res.data;
    },
    enabled: !!deviceId,
  });
}
