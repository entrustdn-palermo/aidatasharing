'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { authAPI } from '@/lib/api';
import { useAuth } from '@/components/auth/AuthProvider';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

interface DemoUser {
  email: string;
  password: string;
  role: string;
  description: string;
  organization: string | null;
  full_name: string;
  is_superuser: boolean;
}

export default function LoginPage() {
  // State initialization with proper client-side guards
  const [mounted, setMounted] = useState(false);
  const [formData, setFormData] = useState({
    email: '',
    password: '',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [selectedDemoUser, setSelectedDemoUser] = useState<string>('');
  const [demoUsers, setDemoUsers] = useState<DemoUser[]>([]);
  const [loadingDemoUsers, setLoadingDemoUsers] = useState(true);
  
  const router = useRouter();
  const { login } = useAuth();

  // Ensure client-side mounting
  useEffect(() => {
    setMounted(true);
  }, []);

  // Use the actual demo users from our seed data
  useEffect(() => {
    if (!mounted) return; // Only run on client side
    
    const fetchDemoUsers = async () => {
      try {
        // First try to get from backend API
        const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const response = await fetch(`${API_BASE_URL}/api/auth/demo-users`);
        if (response.ok) {
          const data = await response.json();
          setDemoUsers(data.demo_users || []);
        } else {
          // Use the actual demo users from our seed data
          setDemoUsers([
            {
              email: "admin@example.com",
              password: "SuperAdmin123!",
              role: "admin",
              description: "System Administrator",
              organization: null,
              full_name: "System Administrator",
              is_superuser: true
            },
            {
              email: "alice@techcorp.com",
              password: "Password123!",
              role: "data_analyst",
              description: "TechCorp Solutions - Data Analyst",
              organization: "TechCorp Solutions",
              full_name: "Alice Johnson",
              is_superuser: false
            },
            {
              email: "bob@dataanalytics.com",
              password: "Password123!",
              role: "data_scientist",
              description: "Data Analytics Inc - Data Scientist",
              organization: "Data Analytics Inc",
              full_name: "Bob Wilson",
              is_superuser: false
            }
          ]);
        }
      } catch (error) {
        console.warn('Error fetching demo users:', error);
        // Fallback to our actual seed data users
        setDemoUsers([
          {
            email: "admin@example.com",
            password: "SuperAdmin123!",
            role: "admin",
            description: "System Administrator",
            organization: null,
            full_name: "System Administrator",
            is_superuser: true
          },
          {
            email: "alice@techcorp.com",
            password: "Password123!",
            role: "data_analyst",
            description: "TechCorp Solutions - Data Analyst",
            organization: "TechCorp Solutions",
            full_name: "Alice Johnson",
            is_superuser: false
          },
          {
            email: "bob@dataanalytics.com",
            password: "Password123!",
            role: "data_scientist",
            description: "Data Analytics Inc - Data Scientist",
            organization: "Data Analytics Inc",
            full_name: "Bob Wilson",
            is_superuser: false
          }
        ]);
      } finally {
        setLoadingDemoUsers(false);
      }
    };

    fetchDemoUsers();
  }, [mounted]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
    // Clear error when user starts typing
    if (errors[name]) {
      setErrors(prev => ({ ...prev, [name]: '' }));
    }
  };

  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.email) {
      newErrors.email = 'Email is required';
    } else if (!/\S+@\S+\.\S+/.test(formData.email)) {
      newErrors.email = 'Email is invalid';
    }

    if (!formData.password) {
      newErrors.password = 'Password is required';
    } else if (formData.password.length < 6) {
      newErrors.password = 'Password must be at least 6 characters';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!validateForm()) return;

    setIsLoading(true);
    try {
      const response = await authAPI.login(formData.email, formData.password);

      if (response.access_token) {
        await login(response.access_token);
        router.push('/dashboard');
      }
    } catch (error: any) {
      console.error('Login error:', error);
      setErrors({
        submit: error.response?.data?.detail || 'Login failed. Please try again.',
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleDemoUserSelect = (value: string) => {
    setSelectedDemoUser(value);
    const user = demoUsers.find(u => u.email === value);
    if (user) {
      setFormData({
        email: user.email,
        password: user.password
      });
      setErrors({});
    }
  };

  // Show loading state while mounting to prevent hydration mismatch
  if (!mounted) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50 flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          <Card variant="elevated" className="shadow-xl">
            <CardContent className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 via-white to-purple-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md animate-fade-in">
        <Card variant="elevated" className="shadow-xl">
          <CardHeader className="text-center pb-6">
            <div className="w-16 h-16 bg-gradient-to-r from-blue-600 to-purple-600 rounded-full flex items-center justify-center mx-auto mb-4">
              <span className="text-2xl">🚀</span>
            </div>
            <CardTitle className="text-2xl font-bold text-gray-900">
              Welcome Back
            </CardTitle>
            <CardDescription className="text-gray-600">
              Sign in to your Entrust Data Sharing MCP Platform account
            </CardDescription>
          </CardHeader>

          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Demo User Selector */}
              <div className="mb-6">
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Quick Login (Demo Accounts)
                </label>
                {loadingDemoUsers ? (
                  <div className="w-full px-4 py-3 border border-gray-300 rounded-lg bg-gray-50 flex items-center justify-center">
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
                    <span className="text-sm text-gray-500">Loading accounts...</span>
                  </div>
                ) : (
                  <Select value={selectedDemoUser} onValueChange={handleDemoUserSelect}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder={`Choose from ${demoUsers.length} demo accounts...`} />
                    </SelectTrigger>
                    <SelectContent className="max-h-80">
                      {demoUsers.map((user) => (
                        <SelectItem key={user.email} value={user.email} className="py-3">
                          <div className="flex flex-col items-start space-y-1">
                            <div className="flex items-center space-x-2">
                              <span className="font-medium text-gray-900">{user.full_name}</span>
                              {user.is_superuser ? (
                                <span className="text-xs bg-red-100 text-red-800 px-2 py-0.5 rounded-full">Admin</span>
                              ) : (
                                <span className="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded-full">User</span>
                              )}
                            </div>
                            <div className="text-sm text-gray-500">{user.email}</div>
                            {user.organization && (
                              <div className="text-xs text-gray-400">🏢 {user.organization}</div>
                            )}
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                <p className="text-xs text-gray-500 mt-1">
                  {loadingDemoUsers ? 'Loading demo accounts...' : `${demoUsers.length} demo accounts available - select one to auto-fill credentials`}
                </p>
              </div>

              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-gray-300" />
                </div>
                <div className="relative flex justify-center text-sm">
                  <span className="px-2 bg-white text-gray-500">or enter manually</span>
                </div>
              </div>

              <div className="space-y-4">
                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                    Email address
                  </label>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                    value={formData.email}
                    onChange={handleChange}
                    className={`w-full px-4 py-3 border rounded-lg shadow-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all ${
                      errors.email ? 'border-red-300 bg-red-50' : 'border-gray-300 hover:border-gray-400'
                    }`}
                    placeholder="Enter your email"
                  />
                  {errors.email && (
                    <p className="mt-2 text-sm text-red-600 flex items-center">
                      <span className="mr-1">⚠️</span>
                      {errors.email}
                    </p>
                  )}
                </div>

                <div>
                  <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-2">
                    Password
                  </label>
                  <input
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={formData.password}
                    onChange={handleChange}
                    className={`w-full px-4 py-3 border rounded-lg shadow-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all ${
                      errors.password ? 'border-red-300 bg-red-50' : 'border-gray-300 hover:border-gray-400'
                    }`}
                    placeholder="Enter your password"
                  />
                  {errors.password && (
                    <p className="mt-2 text-sm text-red-600 flex items-center">
                      <span className="mr-1">⚠️</span>
                      {errors.password}
                    </p>
                  )}
                </div>
              </div>

              {errors.submit && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                  <div className="flex">
                    <div className="flex-shrink-0">
                      <span className="text-red-400">❌</span>
                    </div>
                    <div className="ml-3">
                      <p className="text-sm text-red-800">{errors.submit}</p>
                    </div>
                  </div>
                </div>
              )}

              <Button
                type="submit"
                variant="gradient"
                size="lg"
                isLoading={isLoading}
                className="w-full"
              >
                {isLoading ? 'Signing in...' : 'Sign In'}
              </Button>
            </form>

            <div className="mt-8 text-center">
              <p className="text-sm text-gray-600">
                Don't have an account?{' '}
                <Link
                  href="/register"
                  className="font-medium text-blue-600 hover:text-blue-500 transition-colors"
                >
                  Create one here
                </Link>
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Footer */}
        <div className="text-center mt-8">
          <p className="text-sm text-gray-500">
            Powered by Entrust Data Sharing MCP Platform
          </p>
        </div>
      </div>
    </div>
  );
}