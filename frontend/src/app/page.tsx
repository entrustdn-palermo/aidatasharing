'use client';

import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { useAuth } from "@/components/auth/AuthProvider";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export default function Home() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted && !isLoading && isAuthenticated) {
      router.push('/dashboard');
    }
  }, [mounted, isAuthenticated, isLoading, router]);

  // Show loading during SSR and initial client render
  if (!mounted || isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 via-white to-purple-50">
        <div className="flex flex-col items-center space-y-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600"></div>
          <p className="text-gray-600 animate-pulse">Loading Entrust MCP Platform...</p>
        </div>
      </div>
    );
  }

  // Don't render content if authenticated (will redirect)
  if (isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 via-white to-purple-50">
        <div className="flex flex-col items-center space-y-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-blue-200 border-t-blue-600"></div>
          <p className="text-gray-600">Redirecting to dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50">
      {/* Hero Section */}
      <div className="relative overflow-hidden">
        {/* Background Pattern */}
        <div className="absolute inset-0 bg-grid-pattern opacity-5"></div>
        
        <div className="relative container mx-auto px-4 py-16 sm:py-24">
          <div className="text-center animate-fade-in">
            {/* Hero Badge */}
            <div className="inline-flex items-center rounded-full bg-blue-100 px-4 py-2 text-sm font-medium text-blue-700 mb-8">
              <span className="mr-2">🚀</span>
              Powered by MindsDB Agents
            </div>

            {/* Main Heading */}
            <h1 className="text-4xl sm:text-6xl font-bold text-gray-900 mb-6 leading-tight">
              <span className="text-gradient">Entrust Data Sharing</span>
              <br />
              <span className="text-gray-700">MCP Platform</span>
            </h1>

            {/* Subtitle */}
            <p className="text-xl text-gray-600 mb-8 max-w-3xl mx-auto leading-relaxed">
              Enterprise-grade data sharing platform powered by MindsDB agents.
              Securely share and interact with your data using AI-driven insights.
            </p>
            
            {/* CTA Buttons */}
            <div className="flex flex-col sm:flex-row gap-4 justify-center mb-16">
              <Link href="/login">
                <Button variant="gradient" size="lg" className="w-full sm:w-auto">
                  <span className="mr-2">✨</span>
                  Get Started
                </Button>
              </Link>
              <Link href="/register">
                <Button variant="outline" size="lg" className="w-full sm:w-auto">
                  <span className="mr-2">👤</span>
                  Create Account
                </Button>
              </Link>
            </div>

            {/* Trust Indicators */}
            <div className="flex flex-wrap justify-center items-center gap-8 text-sm text-gray-500">
              <div className="flex items-center">
                <span className="mr-2">⚡</span>
                Lightning Fast
              </div>
              <div className="flex items-center">
                <span className="mr-2">🔒</span>
                Enterprise Secure
              </div>
              <div className="flex items-center">
                <span className="mr-2">🌐</span>
                Cloud Ready
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Features Section */}
      <div className="py-16 bg-white">
        <div className="container mx-auto px-4">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              Why Choose Entrust Data Sharing MCP Platform?
            </h2>
            <p className="text-lg text-gray-600 max-w-2xl mx-auto">
              Built for modern teams who need powerful AI capabilities without the complexity.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            <Card variant="elevated" interactive className="animate-fade-in hover-lift">
              <CardHeader>
                <div className="w-12 h-12 bg-gradient-to-r from-blue-500 to-blue-600 rounded-lg flex items-center justify-center mb-4">
                  <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                </div>
                <CardTitle>Lightning Fast AI Models</CardTitle>
                <CardDescription>
                  Create and deploy machine learning models in minutes, not hours. 
                  MindsDB's powerful engine handles the complexity.
                </CardDescription>
              </CardHeader>
            </Card>

            <Card variant="elevated" interactive className="animate-fade-in hover-lift" style={{ animationDelay: '0.1s' }}>
              <CardHeader>
                <div className="w-12 h-12 bg-gradient-to-r from-green-500 to-green-600 rounded-lg flex items-center justify-center mb-4">
                  <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <CardTitle>Intuitive Management</CardTitle>
                <CardDescription>
                  Beautiful, modern interface that makes complex data operations feel simple. 
                  No technical expertise required.
                </CardDescription>
              </CardHeader>
            </Card>

            <Card variant="elevated" interactive className="animate-fade-in hover-lift" style={{ animationDelay: '0.2s' }}>
              <CardHeader>
                <div className="w-12 h-12 bg-gradient-to-r from-purple-500 to-purple-600 rounded-lg flex items-center justify-center mb-4">
                  <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                </div>
                <CardTitle>Enterprise Security</CardTitle>
                <CardDescription>
                  Bank-level security with JWT authentication, role-based access control, 
                  and comprehensive audit logging.
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </div>
      </div>

      {/* CTA Section */}
      <div className="py-16 bg-gray-50">
        <div className="container mx-auto px-4 text-center">
          <Card variant="elevated" className="max-w-4xl mx-auto">
            <CardContent className="p-12">
              <h2 className="text-3xl font-bold text-gray-900 mb-4">
                Ready to Get Started?
              </h2>
              <p className="text-lg text-gray-600 mb-8 max-w-2xl mx-auto">
                Start sharing and analyzing your data with AI-powered insights.
              </p>
              <div className="flex flex-col sm:flex-row gap-4 justify-center">
                <Link href="/register">
                  <Button variant="gradient" size="lg" className="w-full sm:w-auto">
                    <span className="mr-2">🚀</span>
                    Get Started
                  </Button>
                </Link>
                <Link href="/login">
                  <Button variant="outline" size="lg" className="w-full sm:w-auto">
                    <span className="mr-2">👋</span>
                    Sign In
                  </Button>
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Footer */}
      <footer className="bg-gray-900 text-white py-12">
        <div className="container mx-auto px-4">
          <div className="text-center mb-8">
            <h3 className="text-xl font-bold mb-2">Entrust Data Sharing MCP Platform</h3>
            <p className="text-gray-400 mb-4">
              Empowering organizations with intelligent data sharing and AI-driven insights.
            </p>
          </div>

          {/* Academic Credits */}
          <div className="max-w-2xl mx-auto bg-gray-800 rounded-lg p-6 mb-6">
            <h4 className="text-lg font-semibold mb-4 text-blue-400">Academic Project</h4>
            <div className="space-y-3 text-sm">
              <div className="flex items-start">
                <span className="text-gray-400 min-w-[100px]">Developed by:</span>
                <span className="text-white">Nur Arifin Akbar</span>
              </div>
              <div className="flex items-start">
                <span className="text-gray-400 min-w-[100px]">Institution:</span>
                <span className="text-white">UNIPA (Università degli Studi di Palermo)</span>
              </div>
              <div className="flex items-start">
                <span className="text-gray-400 min-w-[100px]">Supervisors:</span>
                <div className="text-white">
                  <div>Prof. Biagio Lenzitti</div>
                  <div>Prof. Domenico Tegolo</div>
                </div>
              </div>
            </div>
          </div>

          <div className="text-center text-sm text-gray-500">
            Built with FastAPI, Next.js, MindsDB, and PostgreSQL
          </div>
        </div>
      </footer>
    </div>
  )
}