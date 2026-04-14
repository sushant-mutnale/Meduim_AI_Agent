import React from 'react';

export default async function DashboardPage() {
  // Normally we would pre-fetch from the internal Docker network. 
  // For the generated file, we can do client-side or handle empty states gracefully.
  return (
    <main className="min-h-screen bg-gray-50 text-gray-900 p-8">
      <header className="mb-10 flex justify-between items-center">
        <div>
          <h1 className="text-4xl font-bold tracking-tight mb-2 text-indigo-900">Content Engine</h1>
          <p className="text-gray-500">Autopilot AI Content Publishing</p>
        </div>
        <button className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2 rounded-lg font-medium shadow-sm transition">
          Run Pipeline Now
        </button>
      </header>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <section className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
          <h2 className="text-xl font-semibold mb-6 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
            Active System Status
          </h2>
          
          <div className="space-y-4">
            <div className="border border-gray-100 p-4 rounded-xl flex justify-between items-center">
              <div>
                <p className="font-medium">Next Scheduled Run</p>
                <p className="text-sm text-gray-500">in approx. 12 hours</p>
              </div>
              <span className="px-3 py-1 bg-blue-50 text-blue-700 rounded-full text-xs font-semibold">Scheduled</span>
            </div>
            
            <div className="border border-gray-100 p-4 rounded-xl flex justify-between items-center">
              <div>
                <p className="font-medium">Last Execution</p>
                <p className="text-sm text-gray-500">Run ID: #405</p>
              </div>
              <span className="px-3 py-1 bg-green-50 text-green-700 rounded-full text-xs font-semibold">Success</span>
            </div>
          </div>
        </section>
        
        <section className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
          <h2 className="text-xl font-semibold mb-6 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-500"></span>
            Pending Drafts
          </h2>
          
          <div className="space-y-4">
            <div className="border border-gray-100 p-4 rounded-xl">
              <h3 className="font-semibold text-lg text-gray-800">The Future of Agentic Frameworks</h3>
              <p className="text-sm text-gray-600 my-2 line-clamp-2">Agent architectures are evolving away from rigid orchestration frameworks like LangChain towards flexible, code-first Python state machines...</p>
              <div className="flex justify-between items-center mt-4">
                <span className="text-xs font-semibold text-gray-500 bg-gray-100 px-2 py-1 rounded">Confidence: 94%</span>
                <div className="flex gap-2">
                  <button className="text-sm px-4 py-1.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition font-medium">Review</button>
                  <button className="text-sm px-4 py-1.5 bg-emerald-100 hover:bg-emerald-200 text-emerald-800 rounded-lg transition font-medium">Approve</button>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
