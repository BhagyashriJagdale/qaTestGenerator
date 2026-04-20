"""
RAG (Retrieval-Augmented Generation) system for the QA Test Generator.
Uses ChromaDB for vector storage and sentence-transformers for embeddings.
"""

import os
from typing import Optional
from config import get_settings
from rich.console import Console

console = Console()

# Lazy imports to handle optional dependencies
_chromadb = None
_SentenceTransformer = None


def _get_chromadb():
    global _chromadb
    if _chromadb is None:
        import chromadb
        _chromadb = chromadb
    return _chromadb


def _get_sentence_transformer():
    global _SentenceTransformer
    if _SentenceTransformer is None:
        from sentence_transformers import SentenceTransformer
        _SentenceTransformer = SentenceTransformer
    return _SentenceTransformer


class RAGSystem:
    """
    RAG system for retrieving relevant context from past test cases,
    domain knowledge, and QA best practices.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._client = None
        self._collection = None
        self._embedding_model = None
        self._initialized = False
    
    def _lazy_init(self):
        """Initialize ChromaDB and embedding model lazily."""
        if self._initialized:
            return
        
        try:
            chromadb = _get_chromadb()
            SentenceTransformer = _get_sentence_transformer()
            
            # Create persist directory if needed
            os.makedirs(self.settings.chroma_persist_dir, exist_ok=True)
            
            # Initialize ChromaDB
            self._client = chromadb.PersistentClient(
                path=self.settings.chroma_persist_dir
            )
            
            # Get or create collection
            self._collection = self._client.get_or_create_collection(
                name="qa_knowledge_base",
                metadata={"description": "QA test cases and domain knowledge"}
            )
            
            # Initialize embedding model
            self._embedding_model = SentenceTransformer(self.settings.embedding_model)
            
            self._initialized = True
            console.print("[green]✓ RAG system initialized[/green]")
            
        except ImportError as e:
            console.print(f"[yellow]RAG dependencies not installed: {e}[/yellow]")
            console.print("[yellow]RAG features will be disabled[/yellow]")
        except Exception as e:
            console.print(f"[yellow]Could not initialize RAG: {e}[/yellow]")
    
    def add_document(
        self,
        content: str,
        metadata: dict,
        doc_id: Optional[str] = None
    ) -> bool:
        """
        Add a document to the knowledge base.
        
        Args:
            content: The document text
            metadata: Document metadata (domain, type, tags, etc.)
            doc_id: Optional document ID
            
        Returns:
            Success status
        """
        self._lazy_init()
        
        if not self._initialized:
            return False
        
        try:
            # Generate embedding
            embedding = self._embedding_model.encode(content).tolist()
            
            # Generate ID if not provided
            if doc_id is None:
                import hashlib
                doc_id = hashlib.md5(content.encode()).hexdigest()[:12]
            
            # Add to collection
            self._collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata]
            )
            
            return True
            
        except Exception as e:
            console.print(f"[red]Error adding document: {e}[/red]")
            return False
    
    def add_test_case(
        self,
        test_case_content: str,
        feature: str,
        domain: str,
        test_type: str,
        tags: list[str]
    ) -> bool:
        """
        Add a test case to the knowledge base.
        
        Args:
            test_case_content: The test case text or code
            feature: Feature name
            domain: Domain/module name
            test_type: Type of test (manual/api/ui)
            tags: List of tags
            
        Returns:
            Success status
        """
        metadata = {
            "type": "test_case",
            "feature": feature,
            "domain": domain,
            "test_type": test_type,
            "tags": ",".join(tags)
        }
        
        return self.add_document(test_case_content, metadata)
    
    def add_domain_knowledge(
        self,
        content: str,
        domain: str,
        knowledge_type: str
    ) -> bool:
        """
        Add domain knowledge to the knowledge base.
        
        Args:
            content: The knowledge content
            domain: Domain name
            knowledge_type: Type (best_practice, convention, pattern, etc.)
            
        Returns:
            Success status
        """
        metadata = {
            "type": "domain_knowledge",
            "domain": domain,
            "knowledge_type": knowledge_type
        }
        
        return self.add_document(content, metadata)
    
    def search(
        self,
        query: str,
        n_results: int = 5,
        filter_domain: Optional[str] = None,
        filter_type: Optional[str] = None
    ) -> list[dict]:
        """
        Search the knowledge base for relevant context.
        
        Args:
            query: Search query
            n_results: Number of results to return
            filter_domain: Optional domain filter
            filter_type: Optional type filter
            
        Returns:
            List of relevant documents with metadata
        """
        self._lazy_init()
        
        if not self._initialized:
            return []
        
        try:
            # Generate query embedding
            query_embedding = self._embedding_model.encode(query).tolist()
            
            # Build where filter
            where_filter = None
            if filter_domain or filter_type:
                conditions = []
                if filter_domain:
                    conditions.append({"domain": filter_domain})
                if filter_type:
                    conditions.append({"type": filter_type})
                
                if len(conditions) == 1:
                    where_filter = conditions[0]
                else:
                    where_filter = {"$and": conditions}
            
            # Query collection
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where_filter
            )
            
            # Format results
            documents = []
            if results and results['documents']:
                for i, doc in enumerate(results['documents'][0]):
                    documents.append({
                        "content": doc,
                        "metadata": results['metadatas'][0][i] if results['metadatas'] else {},
                        "distance": results['distances'][0][i] if results['distances'] else 0
                    })
            
            return documents
            
        except Exception as e:
            console.print(f"[yellow]RAG search error: {e}[/yellow]")
            return []
    
    def get_context_for_generation(
        self,
        feature_name: str,
        domain: str,
        intent: str,
        n_results: int = 3
    ) -> str:
        """
        Get formatted context for test case generation.
        
        Args:
            feature_name: Name of the feature
            domain: Domain/module
            intent: What the feature does
            n_results: Number of results per query
            
        Returns:
            Formatted context string
        """
        # Build search query
        query = f"{feature_name} {domain} {intent}"
        
        # Search for relevant test cases
        test_cases = self.search(
            query=query,
            n_results=n_results,
            filter_type="test_case"
        )
        
        # Search for domain knowledge
        knowledge = self.search(
            query=query,
            n_results=n_results,
            filter_type="domain_knowledge"
        )
        
        # Format context
        context_parts = []
        
        if test_cases:
            context_parts.append("### Similar Test Cases")
            for i, doc in enumerate(test_cases, 1):
                meta = doc['metadata']
                context_parts.append(f"""
**Example {i}** (Feature: {meta.get('feature', 'N/A')}, Type: {meta.get('test_type', 'N/A')})
{doc['content'][:500]}{'...' if len(doc['content']) > 500 else ''}
""")
        
        if knowledge:
            context_parts.append("\n### Domain Knowledge")
            for doc in knowledge:
                meta = doc['metadata']
                context_parts.append(f"""
**{meta.get('knowledge_type', 'Info').title()}** ({meta.get('domain', 'General')})
{doc['content']}
""")
        
        return "\n".join(context_parts) if context_parts else ""
    
    def get_stats(self) -> dict:
        """Get statistics about the knowledge base."""
        self._lazy_init()
        
        if not self._initialized:
            return {"status": "not initialized", "count": 0}
        
        try:
            count = self._collection.count()
            return {
                "status": "active",
                "count": count,
                "persist_dir": self.settings.chroma_persist_dir
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}


# Singleton instance
_rag_system: Optional[RAGSystem] = None


def get_rag_system() -> RAGSystem:
    """Get or create RAG system singleton."""
    global _rag_system
    if _rag_system is None:
        _rag_system = RAGSystem()
    return _rag_system
