'use client';

import { useOffsetInfiniteQuery } from '@/hooks/useOffsetInfiniteQuery';
import { getGlobalAuditLog } from '@/lib/api/users';
import { useInView } from 'react-intersection-observer';
import React, { useEffect } from 'react';

export default function AdminAuditLogPage() {
  const {
    data,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    status,
  } = useOffsetInfiniteQuery(['global-audit'], (pageIndex) => getGlobalAuditLog(pageIndex, 20));

  const { ref, inView } = useInView();

  useEffect(() => {
    if (inView && hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [inView, hasNextPage, isFetchingNextPage, fetchNextPage]);

  return (
    <div className="container mx-auto p-4 max-w-6xl mt-8">
      <h1 className="text-2xl font-bold mb-6">Global Audit Log (Admin)</h1>
      
      {status === 'pending' ? (
        <p>Loading...</p>
      ) : status === 'error' ? (
        <div className="p-3 bg-red-50 text-red-700 rounded-md">
          {error instanceof Error ? error.message : 'Error fetching audit log'}
        </div>
      ) : (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">ID</th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date</th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Action</th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">User ID</th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actor ID</th>
                  <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Description</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {data.pages.map((page, i) => (
                  <React.Fragment key={i}>
                    {page.data.map((entry) => (
                      <tr key={entry.id}>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{entry.id}</td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{new Date(entry.created_at).toLocaleString()}</td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                            {entry.action}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 truncate max-w-xs" title={entry.user_id}>{entry.user_id}</td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 truncate max-w-xs" title={entry.actor_user_id}>{entry.actor_user_id}</td>
                        <td className="px-6 py-4 text-sm text-gray-500">{entry.description}</td>
                      </tr>
                    ))}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
          
          <div className="p-4 border-t border-gray-200 text-center">
            <div ref={ref}>
              {isFetchingNextPage
                ? 'Loading more...'
                : hasNextPage
                ? 'Load More'
                : 'Nothing more to load'}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
