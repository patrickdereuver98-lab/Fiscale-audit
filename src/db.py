"""
FiscAudit AI - Database Client
Supabase (PostgreSQL) integration met CRUD operaties voor audit runs.
"""

import json
from typing import List, Dict, Optional, Any
from datetime import datetime
from uuid import uuid4

from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions

from .matcher import MatchResult, AuditSummary
from .advisor import RiskAssessment


# ============================================================================
# SUPABASE CLIENT WRAPPER
# ============================================================================

class SupabaseClient:
    """
    Wrapper rond Supabase client met FiscAudit-specifieke operaties.
    """
    
    def __init__(self, url: str, key: str):
        """
        Parameters:
        -----------
        url : str
            Supabase project URL
        key : str
            Supabase public key (anon key)
        """
        self.url = url
        self.key = key
        
        # Creëer Supabase client
        options = ClientOptions(
            auto_refresh_token=True,
            persist_session=True,
            storage=None  # In-memory voor Streamlit
        )
        
        self.db: Client = create_client(url, key, options)
    
    # ========================================================================
    # DOSSIER OPERATIONS
    # ========================================================================
    
    def create_dossier(self, 
                      klant_naam: str,
                      klant_email: Optional[str] = None,
                      aangiftejaar: int = 2024,
                      beschrijving: str = "") -> str:
        """
        Creëer een nieuw dossier.
        
        Returns:
        --------
        str
            UUID van het nieuwe dossier
        """
        try:
            data = {
                "klant_naam": klant_naam,
                "klant_email": klant_email,
                "aangiftejaar": aangiftejaar,
                "notities": beschrijving,
                "status": "in_progress",
                "created_at": datetime.now().isoformat()
            }
            
            response = self.db.table("dossiers").insert(data).execute()
            
            if response.data:
                return response.data[0]["id"]
            raise ValueError("Dossier creation failed")
            
        except Exception as e:
            raise RuntimeError(f"Dossier creation error: {str(e)}")
    
    def get_dossier(self, dossier_id: str) -> Optional[Dict]:
        """Haal dossier op"""
        try:
            response = self.db.table("dossiers").select("*").eq("id", dossier_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error fetching dossier: {e}")
            return None
    
    def list_dossiers(self, limit: int = 50) -> List[Dict]:
        """Lijst alle dossiers op"""
        try:
            response = self.db.table("dossiers").select("*").order("created_at", desc=True).limit(limit).execute()
            return response.data or []
        except Exception as e:
            print(f"Error listing dossiers: {e}")
            return []
    
    def update_dossier_status(self, dossier_id: str, status: str, notities: str = ""):
        """Update dossier status"""
        try:
            data = {
                "status": status,
                "notities": notities,
                "updated_at": datetime.now().isoformat()
            }
            self.db.table("dossiers").update(data).eq("id", dossier_id).execute()
        except Exception as e:
            print(f"Error updating dossier: {e}")
    
    # ========================================================================
    # AUDIT RESULTS OPERATIONS
    # ========================================================================
    
    def save_audit_results(self, 
                          dossier_id: str,
                          results: List[MatchResult]) -> bool:
        """
        Sla audit-resultaten op (batch insert).
        """
        try:
            # Converteer naar database format
            records = []
            for result in results:
                records.append({
                    "dossier_id": dossier_id,
                    "ag_code": result.ag_code,
                    "status": result.status.value,
                    "bedrag_aangifte": float(result.bedrag_aangifte) if result.bedrag_aangifte else None,
                    "bedrag_document": float(result.bedrag_document) if result.bedrag_document else None,
                    "verschil": float(result.verschil) if result.verschil else None,
                    "opmerking": result.opmerking,
                    "document_ref": result.document_bron,
                    "created_at": result.timestamp
                })
            
            # Batch insert
            self.db.table("audit_results").insert(records).execute()
            return True
            
        except Exception as e:
            print(f"Error saving audit results: {e}")
            return False
    
    def get_audit_results(self, dossier_id: str) -> List[Dict]:
        """Haal audit-resultaten voor dossier op"""
        try:
            response = self.db.table("audit_results").select("*").eq("dossier_id", dossier_id).execute()
            return response.data or []
        except Exception as e:
            print(f"Error fetching audit results: {e}")
            return []
    
    def get_audit_summary(self, dossier_id: str) -> Dict:
        """Haal audit-samenvatting op (via SQL view)"""
        try:
            response = self.db.table("dossier_summary").select("*").eq("id", dossier_id).execute()
            return response.data[0] if response.data else {}
        except Exception as e:
            print(f"Error fetching audit summary: {e}")
            return {}
    
    # ========================================================================
    # FISCAL NOTES OPERATIONS
    # ========================================================================
    
    def save_fiscal_notes(self,
                         dossier_id: str,
                         assessment: RiskAssessment) -> bool:
        """
        Sla fiscale analyse op.
        """
        try:
            data = {
                "dossier_id": dossier_id,
                "risk_level": assessment.overall_risk.value,
                "risico_analyse": json.dumps(assessment.to_dict(), ensure_ascii=False),
                "kritieke_punten": json.dumps(
                    [rp.__dict__ for rp in assessment.risico_punten],
                    ensure_ascii=False,
                    default=str
                ),
                "klant_mail_concept": assessment.klant_email_concept,
                "created_at": datetime.now().isoformat()
            }
            
            self.db.table("fiscal_notes").insert(data).execute()
            return True
            
        except Exception as e:
            print(f"Error saving fiscal notes: {e}")
            return False
    
    def get_fiscal_notes(self, dossier_id: str) -> Optional[Dict]:
        """Haal fiscale noten op"""
        try:
            response = self.db.table("fiscal_notes").select("*").eq("dossier_id", dossier_id).order("created_at", desc=True).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            print(f"Error fetching fiscal notes: {e}")
            return None
    
    # ========================================================================
    # DOCUMENT OPERATIONS
    # ========================================================================
    
    def save_uploaded_document(self,
                              dossier_id: str,
                              bestandsnaam: str,
                              document_type: str,
                              extracted_data: Dict) -> bool:
        """
        Sla info van geüploade document op.
        """
        try:
            data = {
                "dossier_id": dossier_id,
                "bestandsnaam": bestandsnaam,
                "document_type": document_type,
                "extracted_data": json.dumps(extracted_data, ensure_ascii=False, default=str),
                "created_at": datetime.now().isoformat()
            }
            
            self.db.table("uploaded_documents").insert(data).execute()
            return True
            
        except Exception as e:
            print(f"Error saving document metadata: {e}")
            return False
    
    def get_dossier_documents(self, dossier_id: str) -> List[Dict]:
        """Haal alle documenten voor dossier op"""
        try:
            response = self.db.table("uploaded_documents").select("*").eq("dossier_id", dossier_id).execute()
            return response.data or []
        except Exception as e:
            print(f"Error fetching documents: {e}")
            return []
    
    # ========================================================================
    # AUDIT LOG OPERATIONS
    # ========================================================================
    
    def log_action(self,
                  dossier_id: str,
                  action: str,
                  details: Dict = None,
                  user_info: str = "system",
                  ip_address: str = "0.0.0.0") -> bool:
        """
        Log een audit-actie (compliance trail).
        """
        try:
            data = {
                "dossier_id": dossier_id,
                "action": action,
                "user_info": user_info,
                "ip_address": ip_address,
                "details": json.dumps(details or {}, ensure_ascii=False),
                "created_at": datetime.now().isoformat()
            }
            
            self.db.table("audit_logs").insert(data).execute()
            return True
            
        except Exception as e:
            print(f"Error logging action: {e}")
            return False
    
    def get_audit_log(self, dossier_id: str, limit: int = 100) -> List[Dict]:
        """Haal audit log op"""
        try:
            response = self.db.table("audit_logs").select("*").eq("dossier_id", dossier_id).order("created_at", desc=True).limit(limit).execute()
            return response.data or []
        except Exception as e:
            print(f"Error fetching audit log: {e}")
            return []
    
    # ========================================================================
    # REPORTING & ANALYTICS
    # ========================================================================
    
    def get_statistics(self) -> Dict:
        """Haal overall statistieken op"""
        try:
            stats = {
                "total_dossiers": 0,
                "completed": 0,
                "in_progress": 0,
                "total_mismatches": 0,
                "avg_accuracy": 0.0
            }
            
            # Total dossiers
            response = self.db.table("dossiers").select("id").execute()
            stats["total_dossiers"] = len(response.data or [])
            
            # Completed vs in progress
            response = self.db.table("dossiers").select("status").execute()
            for item in response.data or []:
                if item["status"] == "completed":
                    stats["completed"] += 1
                elif item["status"] == "in_progress":
                    stats["in_progress"] += 1
            
            return stats
            
        except Exception as e:
            print(f"Error fetching statistics: {e}")
            return {}
    
    def export_dossier_report(self, dossier_id: str) -> Dict:
        """Export volledige dossier-rapport"""
        try:
            dossier = self.get_dossier(dossier_id)
            audit_results = self.get_audit_results(dossier_id)
            fiscal_notes = self.get_fiscal_notes(dossier_id)
            documents = self.get_dossier_documents(dossier_id)
            audit_log = self.get_audit_log(dossier_id)
            
            report = {
                "dossier": dossier,
                "audit_results": audit_results,
                "fiscal_analysis": fiscal_notes,
                "documents": documents,
                "audit_log": audit_log,
                "export_date": datetime.now().isoformat()
            }
            
            return report
            
        except Exception as e:
            print(f"Error exporting report: {e}")
            return {}
    
    # ========================================================================
    # MAINTENANCE
    # ========================================================================
    
    def delete_dossier(self, dossier_id: str) -> bool:
        """
        Verwijder dossier (cascade delete door RLS).
        """
        try:
            # Log action first
            self.log_action(dossier_id, "dossier_deleted")
            
            # Delete
            self.db.table("dossiers").delete().eq("id", dossier_id).execute()
            return True
            
        except Exception as e:
            print(f"Error deleting dossier: {e}")
            return False
    
    def health_check(self) -> bool:
        """Controleer databaseconnectie"""
        try:
            response = self.db.table("dossiers").select("id").limit(1).execute()
            return True
        except Exception as e:
            print(f"Database health check failed: {e}")
            return False


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def initialize_supabase(url: str, key: str) -> SupabaseClient:
    """Factory function voor Supabase client"""
    try:
        client = SupabaseClient(url, key)
        if client.health_check():
            print("✓ Connected to Supabase")
            return client
        else:
            raise RuntimeError("Health check failed")
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Supabase: {str(e)}")


if __name__ == "__main__":
    print("Database client module loaded")
    print("Use: client = SupabaseClient(url, key)")
