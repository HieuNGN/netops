import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { networksApi } from '../api';

export function useNetworks() {
  const queryClient = useQueryClient();

  const { data, isLoading, error } = useQuery({
    queryKey: ['networks'],
    queryFn: async () => {
      const response = await networksApi.list();
      return response.data;
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: { name: string; cidr?: string; description?: string }) =>
      networksApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['networks'] });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
      networksApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['networks'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => networksApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['networks'] });
    },
  });

  const setDefaultMutation = useMutation({
    mutationFn: (id: string) => networksApi.setDefault(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['networks'] });
    },
  });

  return {
    networks: data || [],
    isLoading,
    error,
    createNetwork: createMutation.mutateAsync,
    updateNetwork: updateMutation.mutateAsync,
    deleteNetwork: deleteMutation.mutateAsync,
    setDefaultNetwork: setDefaultMutation.mutateAsync,
    isCreating: createMutation.isPending,
    isUpdating: updateMutation.isPending,
    isDeleting: deleteMutation.isPending,
  };
}
