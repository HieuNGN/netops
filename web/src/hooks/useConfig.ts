import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { configApi, discoveryApi } from '../api';
import type { EnvironmentProfileInfo, TrapConfig } from '../api';

export function useEnvironmentProfiles() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['config-profiles'],
    queryFn: async () => {
      const response = await configApi.profiles();
      return response.data;
    },
    staleTime: 30_000,
  });

  return {
    profiles: (data?.profiles || []) as EnvironmentProfileInfo[],
    activeProfile: data?.active_profile || 'homelab',
    detectedProfile: data?.detected_profile || 'homelab',
    isGuessed: data?.is_guessed || false,
    isLoading,
    error,
  };
}

export function useSetProfile() {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ profile, confirmed }: { profile: string; confirmed?: boolean }) =>
      configApi.setProfile(profile, confirmed),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config-profiles'] });
      queryClient.invalidateQueries({ queryKey: ['config'] });
    },
  });
  return mutation;
}

export function useTrapConfig() {
  const { data, isLoading, error } = useQuery<TrapConfig>({
    queryKey: ['config-traps'],
    queryFn: async () => {
      const response = await configApi.traps();
      return response.data;
    },
    refetchInterval: 5000,
  });

  const queryClient = useQueryClient();
  const setMutation = useMutation({
    mutationFn: (updates: Partial<TrapConfig>) => configApi.setTraps(updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config-traps'] });
    },
  });

  return {
    trapConfig: data,
    isLoading,
    error,
    setTraps: setMutation.mutateAsync,
    trapsMutation: setMutation,
  };
}

export function useStaleAction() {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'delete' | 'keep' }) =>
      discoveryApi.staleAction(id, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices'] });
    },
  });
  return mutation;
}
