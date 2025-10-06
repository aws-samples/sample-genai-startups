import React, { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { useToast } from '@/hooks/use-toast';
import { Toaster } from '@/components/ui/toaster';
import {
  Search,
  FileText,
  Download,
  MessageSquare,
  Upload,
  Loader2,
  CheckCircle,
  AlertCircle,
  Clock,
  Zap,
  Brain,
  FileSearch,
  Globe
} from 'lucide-react';

const Dashboard = () => {
  const [activeRequests, setActiveRequests] = useState(new Map());
  const [completedRequests, setCompletedRequests] = useState([]);
  const { toast } = useToast();

  // Form states for different tools
  const [searchQuery, setSearchQuery] = useState('');
  const [documentQuery, setDocumentQuery] = useState('');
  const [documentFile, setDocumentFile] = useState(null);
  const [htmlContent, setHtmlContent] = useState('');
  const [humanReviewQuery, setHumanReviewQuery] = useState('');
  const [humanReviewFile, setHumanReviewFile] = useState(null);

  const generateRequestId = () => `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

  const simulateToolExecution = async (toolName, requestId, duration = 3000) => {
    // Add to active requests
    setActiveRequests(prev => new Map(prev.set(requestId, {
      id: requestId,
      tool: toolName,
      status: 'processing',
      progress: 0,
      startTime: new Date()
    })));

    // Simulate progress
    const progressInterval = setInterval(() => {
      setActiveRequests(prev => {
        const newMap = new Map(prev);
        const request = newMap.get(requestId);
        if (request && request.progress < 90) {
          request.progress = Math.min(90, request.progress + Math.random() * 20);
          newMap.set(requestId, request);
        }
        return newMap;
      });
    }, 500);

    // Complete after duration
    setTimeout(() => {
      clearInterval(progressInterval);
      
      setActiveRequests(prev => {
        const newMap = new Map(prev);
        newMap.delete(requestId);
        return newMap;
      });

      const completedRequest = {
        id: requestId,
        tool: toolName,
        status: 'completed',
        completedAt: new Date(),
        result: `${toolName} completed successfully`
      };

      setCompletedRequests(prev => [completedRequest, ...prev.slice(0, 9)]);
      
      toast({
        title: "Tool Completed",
        description: `${toolName} has finished processing your request.`,
      });
    }, duration);
  };

  const handleSearchAgent = async () => {
    if (!searchQuery.trim()) {
      toast({
        title: "Error",
        description: "Please enter a search query.",
        variant: "destructive",
      });
      return;
    }

    const requestId = generateRequestId();
    toast({
      title: "Search Agent Started",
      description: "Searching the web and generating summary...",
    });

    await simulateToolExecution('Search Agent', requestId, 4000);
    setSearchQuery('');
  };

  const handleDocumentQuerier = async () => {
    if (!documentQuery.trim() || !documentFile) {
      toast({
        title: "Error",
        description: "Please provide both a query and upload a document.",
        variant: "destructive",
      });
      return;
    }

    const requestId = generateRequestId();
    toast({
      title: "Document Querier Started",
      description: "Analyzing document and processing query...",
    });

    await simulateToolExecution('Document Querier', requestId, 5000);
    setDocumentQuery('');
    setDocumentFile(null);
  };

  const handlePDFGenerator = async () => {
    if (!htmlContent.trim()) {
      toast({
        title: "Error",
        description: "Please provide HTML content to convert.",
        variant: "destructive",
      });
      return;
    }

    const requestId = generateRequestId();
    toast({
      title: "PDF Generator Started",
      description: "Converting HTML to PDF...",
    });

    await simulateToolExecution('PDF Generator', requestId, 3000);
    setHtmlContent('');
  };

  const handleHumanReview = async () => {
    if (!humanReviewQuery.trim() || !humanReviewFile) {
      toast({
        title: "Error",
        description: "Please provide both a query and upload a document for review.",
        variant: "destructive",
      });
      return;
    }

    const requestId = generateRequestId();
    toast({
      title: "Human Review Requested",
      description: "Your request has been submitted for human review.",
    });

    // For human review, we don't auto-complete - it goes to the reviewer dashboard
    setActiveRequests(prev => new Map(prev.set(requestId, {
      id: requestId,
      tool: 'Human Review',
      status: 'pending_review',
      progress: 100,
      startTime: new Date()
    })));

    setHumanReviewQuery('');
    setHumanReviewFile(null);
  };

  const getToolIcon = (toolName) => {
    switch (toolName) {
      case 'Search Agent': return <Globe className="h-4 w-4" />;
      case 'Document Querier': return <FileSearch className="h-4 w-4" />;
      case 'PDF Generator': return <FileText className="h-4 w-4" />;
      case 'Human Review': return <MessageSquare className="h-4 w-4" />;
      default: return <Zap className="h-4 w-4" />;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'processing': return 'default';
      case 'completed': return 'secondary';
      case 'pending_review': return 'destructive';
      default: return 'outline';
    }
  };

  return (
    <div className="container mx-auto px-4 py-8">
      {/* Hero Section */}
      <div className="text-center mb-12">
        <div className="flex items-center justify-center mb-4">
          <Brain className="h-12 w-12 text-primary mr-3" />
          <div>
            <h1 className="text-4xl font-bold tracking-tight">AI Agent Platform</h1>
            <p className="text-xl text-muted-foreground mt-2">
              Powerful AI tools for search, document analysis, and content generation
            </p>
          </div>
        </div>
      </div>

      {/* Active Requests */}
      {activeRequests.size > 0 && (
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <Clock className="h-5 w-5" />
              <span>Active Requests</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {Array.from(activeRequests.values()).map((request) => (
                <div key={request.id} className="flex items-center space-x-4 p-4 border rounded-lg">
                  <div className="flex items-center space-x-2">
                    {getToolIcon(request.tool)}
                    <span className="font-medium">{request.tool}</span>
                  </div>
                  <div className="flex-1">
                    <Progress value={request.progress} className="w-full" />
                  </div>
                  <Badge variant={getStatusColor(request.status)}>
                    {request.status === 'pending_review' ? 'Pending Review' : 'Processing'}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Tools Tabs */}
      <Tabs defaultValue="search" className="space-y-6">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="search" className="flex items-center space-x-2">
            <Globe className="h-4 w-4" />
            <span>Search Agent</span>
          </TabsTrigger>
          <TabsTrigger value="document" className="flex items-center space-x-2">
            <FileSearch className="h-4 w-4" />
            <span>Document Querier</span>
          </TabsTrigger>
          <TabsTrigger value="pdf" className="flex items-center space-x-2">
            <FileText className="h-4 w-4" />
            <span>PDF Generator</span>
          </TabsTrigger>
          <TabsTrigger value="review" className="flex items-center space-x-2">
            <MessageSquare className="h-4 w-4" />
            <span>Human Review</span>
          </TabsTrigger>
        </TabsList>

        {/* Search Agent */}
        <TabsContent value="search">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <Globe className="h-5 w-5" />
                <span>Search Agent</span>
              </CardTitle>
              <CardDescription>
                Search the web using Brave Search API and get AI-powered summaries via Bedrock
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="search-query">Search Query</Label>
                <Input
                  id="search-query"
                  placeholder="Enter your search query..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
              <Button onClick={handleSearchAgent} className="w-full">
                <Search className="mr-2 h-4 w-4" />
                Start Search
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Document Querier */}
        <TabsContent value="document">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <FileSearch className="h-5 w-5" />
                <span>Document Querier</span>
              </CardTitle>
              <CardDescription>
                Upload a document and ask questions about its content using AI analysis
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="doc-query">Query</Label>
                <Textarea
                  id="doc-query"
                  placeholder="What would you like to know about the document?"
                  value={documentQuery}
                  onChange={(e) => setDocumentQuery(e.target.value)}
                  rows={3}
                />
              </div>
              <div>
                <Label htmlFor="doc-file">Upload Document</Label>
                <Input
                  id="doc-file"
                  type="file"
                  accept=".pdf,.doc,.docx,.txt"
                  onChange={(e) => setDocumentFile(e.target.files[0])}
                />
              </div>
              <Button onClick={handleDocumentQuerier} className="w-full">
                <FileSearch className="mr-2 h-4 w-4" />
                Analyze Document
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* PDF Generator */}
        <TabsContent value="pdf">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <FileText className="h-5 w-5" />
                <span>PDF Generator</span>
              </CardTitle>
              <CardDescription>
                Convert HTML content to PDF using Puppeteer and store on S3
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="html-content">HTML Content</Label>
                <Textarea
                  id="html-content"
                  placeholder="Enter HTML content to convert to PDF..."
                  value={htmlContent}
                  onChange={(e) => setHtmlContent(e.target.value)}
                  rows={8}
                  className="font-mono text-sm"
                />
              </div>
              <Button onClick={handlePDFGenerator} className="w-full">
                <Download className="mr-2 h-4 w-4" />
                Generate PDF
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Human Review */}
        <TabsContent value="review">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center space-x-2">
                <MessageSquare className="h-5 w-5" />
                <span>Human Review Request</span>
              </CardTitle>
              <CardDescription>
                Submit documents and queries for human expert review and approval
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label htmlFor="review-query">Review Request</Label>
                <Textarea
                  id="review-query"
                  placeholder="Describe what you need reviewed and any specific questions..."
                  value={humanReviewQuery}
                  onChange={(e) => setHumanReviewQuery(e.target.value)}
                  rows={4}
                />
              </div>
              <div>
                <Label htmlFor="review-file">Upload Document for Review</Label>
                <Input
                  id="review-file"
                  type="file"
                  accept=".pdf,.doc,.docx,.txt"
                  onChange={(e) => setHumanReviewFile(e.target.files[0])}
                />
              </div>
              <Button onClick={handleHumanReview} className="w-full" variant="outline">
                <MessageSquare className="mr-2 h-4 w-4" />
                Request Human Review
              </Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Recent Completions */}
      {completedRequests.length > 0 && (
        <Card className="mt-8">
          <CardHeader>
            <CardTitle className="flex items-center space-x-2">
              <CheckCircle className="h-5 w-5" />
              <span>Recent Completions</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {completedRequests.map((request) => (
                <div key={request.id} className="flex items-center justify-between p-3 border rounded-lg">
                  <div className="flex items-center space-x-3">
                    {getToolIcon(request.tool)}
                    <span className="font-medium">{request.tool}</span>
                    <Badge variant="secondary">Completed</Badge>
                  </div>
                  <span className="text-sm text-muted-foreground">
                    {request.completedAt.toLocaleTimeString()}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <Toaster />
    </div>
  );
};

export default Dashboard;
