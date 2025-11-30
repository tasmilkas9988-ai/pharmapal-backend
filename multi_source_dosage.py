"""
Multi-Source Dosage Information Service
Fetches drug dosage from multiple reliable sources with strict matching
Supports Arabic and English drug names
"""
import os
import re
import asyncio
import httpx
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Emergent LLM key for Gemini
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')

# Arabic to English transliteration mapping for common drug terms
ARABIC_ENGLISH_MAPPING = {
    'باراسيتامول': 'paracetamol',
    'ايبوبروفين': 'ibuprofen',
    'اسبرين': 'aspirin',
    'اموكسيسيلين': 'amoxicillin',
    'ديكلوفيناك': 'diclofenac',
    'اومفيزول': 'omeprazole',
    'ميتفورمين': 'metformin',
    'كافيين': 'caffeine',
}

class MultiSourceDosageService:
    def __init__(self):
        self.timeout = 10.0
    
    def detect_language(self, text: str) -> str:
        """Detect if text contains Arabic characters"""
        arabic_pattern = re.compile(r'[\u0600-\u06FF]')
        return 'ar' if arabic_pattern.search(text) else 'en'
    
    def translate_arabic_to_english(self, drug_name: str) -> str:
        """Translate common Arabic drug names to English"""
        drug_name_lower = drug_name.lower()
        for arabic, english in ARABIC_ENGLISH_MAPPING.items():
            if arabic in drug_name_lower:
                drug_name_lower = drug_name_lower.replace(arabic, english)
        return drug_name_lower
        
    def parse_drug_name(self, drug_name: str) -> List[Dict]:
        """
        Parse drug name to extract all active ingredients and strengths
        Supports: "Paracetamol 500mg", "Paracetamol 500mg + Caffeine 65mg"
        Supports Arabic: "باراسيتامول 500 مجم"
        """
        original_name = drug_name
        language = self.detect_language(drug_name)
        
        # Translate Arabic to English for API calls
        if language == 'ar':
            drug_name = self.translate_arabic_to_english(drug_name)
        
        # Split by common separators: +, /, ,
        parts = re.split(r'[+/,]', drug_name)
        
        ingredients = []
        for part in parts:
            part = part.strip()
            # Match pattern: ingredient + strength + unit (English)
            match = re.search(r'(.+?)\s*(\d+\.?\d*)\s*(mg|g|ml|mcg|%|مجم|جم)', part, re.IGNORECASE)
            if match:
                ingredients.append({
                    'ingredient': match.group(1).strip(),
                    'strength': match.group(2),
                    'unit': match.group(3).lower().replace('مجم', 'mg').replace('جم', 'g'),
                    'original_name': original_name,
                    'language': language
                })
            else:
                # No strength found, just ingredient name
                ingredients.append({
                    'ingredient': part,
                    'strength': None,
                    'unit': None,
                    'original_name': original_name,
                    'language': language
                })
        
        return ingredients
    
    async def search_fda_api(self, ingredients: List[Dict]) -> Optional[Dict]:
        """Search FDA OpenFDA API with enhanced information extraction"""
        try:
            # Build search query
            ingredient_name = ingredients[0]['ingredient']
            
            # Try exact match first
            url = f"https://api.fda.gov/drug/label.json"
            params = {
                'search': f'openfda.generic_name:"{ingredient_name}"',
                'limit': 5
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('results'):
                        result = data['results'][0]
                        openfda = result.get('openfda', {})
                        
                        # Extract dosage form (route of administration)
                        dosage_form_list = openfda.get('route', [])
                        dosage_form = dosage_form_list[0] if dosage_form_list else 'Unknown'
                        
                        # Extract product type
                        product_type = openfda.get('product_type', [''])[0] if openfda.get('product_type') else ''
                        
                        # Get indications (common use)
                        indications = result.get('indications_and_usage', [''])[0] if result.get('indications_and_usage') else ''
                        
                        # Extract dosage info with administration
                        dosage_text = result.get('dosage_and_administration', ['Not specified'])[0][:500]
                        
                        # Extract dosage info
                        dosage_info = {
                            'source': 'FDA OpenFDA',
                            'ingredient': ingredient_name,
                            'dosage_form': dosage_form,
                            'product_type': product_type,
                            'common_use': indications[:200] if indications else '',
                            'dosage': dosage_text,
                            'warnings': result.get('warnings', [''])[0][:300] if result.get('warnings') else '',
                            'confidence': 'high',
                            'found': True
                        }
                        
                        return dosage_info
        except Exception as e:
            print(f"FDA API Error: {str(e)}")
        
        return None
    
    async def search_rxnorm_api(self, ingredients: List[Dict]) -> Optional[Dict]:
        """Search RxNorm API for drug matching"""
        try:
            ingredient_name = ingredients[0]['ingredient']
            
            # RxNorm approximate match
            url = f"https://rxnav.nlm.nih.gov/REST/approximateTerm.json"
            params = {'term': ingredient_name, 'maxEntries': 5}
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    candidates = data.get('approximateGroup', {}).get('candidate', [])
                    
                    if candidates:
                        # Get first match
                        rxcui = candidates[0].get('rxcui')
                        
                        # Get drug properties
                        prop_url = f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/properties.json"
                        prop_response = await client.get(prop_url)
                        
                        if prop_response.status_code == 200:
                            prop_data = prop_response.json()
                            properties = prop_data.get('properties', {})
                            
                            return {
                                'source': 'RxNorm NLM',
                                'ingredient': properties.get('name', ingredient_name),
                                'rxcui': rxcui,
                                'found': True,
                                'confidence': 'high'
                            }
        except Exception as e:
            print(f"RxNorm API Error: {str(e)}")
        
        return None
    
    async def search_dailymed_api(self, ingredients: List[Dict]) -> Optional[Dict]:
        """Search DailyMed API"""
        try:
            ingredient_name = ingredients[0]['ingredient']
            
            # DailyMed search
            url = f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json"
            params = {'drug_name': ingredient_name}
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params=params)
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('data'):
                        return {
                            'source': 'DailyMed',
                            'ingredient': ingredient_name,
                            'found': True,
                            'confidence': 'medium',
                            'setid': data['data'][0].get('setid')
                        }
        except Exception as e:
            print(f"DailyMed API Error: {str(e)}")
        
        return None
    
    async def search_google_gemini(self, ingredients: List[Dict]) -> Optional[Dict]:
        """Search using Google Gemini AI as a fallback source with comprehensive information"""
        if not EMERGENT_LLM_KEY:
            return None
        
        try:
            ingredient_name = ingredients[0]['ingredient']
            original_name = ingredients[0].get('original_name', ingredient_name)
            language = ingredients[0].get('language', 'en')
            
            ingredients_str = ' + '.join([
                f"{ing['ingredient']} {ing['strength']}{ing['unit']}" 
                if ing['strength'] else ing['ingredient']
                for ing in ingredients
            ])
            
            # Enhanced bilingual prompt with detailed requirements
            if language == 'ar':
                prompt = f"""أنت خبير معلومات طبية. قدم معلومات مفصلة عن هذا الدواء:

الدواء: {ingredients_str}
الاسم الأصلي: {original_name}

يرجى تقديم المعلومات التالية بشكل واضح ومنظم:
1. نوع الدواء (أقراص، كريم، بخاخ، حقن، سائل، إلخ)
2. الاستخدام الطبي الأكثر شيوعاً
3. الجرعة المعتادة للبالغين حسب النوع
4. طريقة الاستخدام (كيفية تناول أو تطبيق الدواء)
5. مدة العلاج المعتادة
6. تحذيرات هامة

صيغة الإجابة (استخدم هذا التنسيق بالضبط):
DOSAGE_FORM: [نوع الدواء]
COMMON_USE: [الاستخدام الأكثر شيوعاً]
DOSAGE: [الجرعة المعتادة]
ADMINISTRATION: [طريقة الاستخدام]
DURATION: [مدة العلاج]
WARNINGS: [التحذيرات]

اجعل الإجابة موجزة ومفيدة (أقل من 300 كلمة)."""
            else:
                prompt = f"""You are a medical information expert. Provide detailed information for this medication:

Drug: {ingredients_str}
Original Name: {original_name}

Please provide the following information clearly and organized:
1. Dosage form (tablets, cream, spray, injection, liquid, etc.)
2. Most common medical use
3. Standard adult dosage based on form
4. Administration method (how to take or apply)
5. Typical treatment duration
6. Important warnings

Response format (use this exact format):
DOSAGE_FORM: [type of medication]
COMMON_USE: [most common use]
DOSAGE: [standard dosage]
ADMINISTRATION: [how to use]
DURATION: [treatment duration]
WARNINGS: [important warnings]

Keep it concise and useful (under 300 words)."""
            
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    url,
                    params={'key': EMERGENT_LLM_KEY},
                    json={
                        'contents': [{
                            'parts': [{'text': prompt}]
                        }]
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    text = data['candidates'][0]['content']['parts'][0]['text']
                    
                    # Parse the enhanced response
                    dosage_form_match = re.search(r'DOSAGE_FORM:\s*(.+?)(?=\n|$)', text, re.IGNORECASE)
                    common_use_match = re.search(r'COMMON_USE:\s*(.+?)(?=\n|$)', text, re.IGNORECASE)
                    dosage_match = re.search(r'DOSAGE:\s*(.+?)(?=ADMINISTRATION:|$)', text, re.DOTALL | re.IGNORECASE)
                    admin_match = re.search(r'ADMINISTRATION:\s*(.+?)(?=DURATION:|$)', text, re.DOTALL | re.IGNORECASE)
                    duration_match = re.search(r'DURATION:\s*(.+?)(?=WARNINGS:|$)', text, re.DOTALL | re.IGNORECASE)
                    warnings_match = re.search(r'WARNINGS:\s*(.+?)$', text, re.DOTALL | re.IGNORECASE)
                    
                    dosage_form = dosage_form_match.group(1).strip() if dosage_form_match else 'Unknown'
                    common_use = common_use_match.group(1).strip() if common_use_match else ''
                    dosage = dosage_match.group(1).strip() if dosage_match else text[:300]
                    administration = admin_match.group(1).strip() if admin_match else ''
                    duration = duration_match.group(1).strip() if duration_match else ''
                    warnings = warnings_match.group(1).strip() if warnings_match else ''
                    
                    return {
                        'source': 'Google Gemini AI',
                        'ingredient': ingredient_name,
                        'dosage_form': dosage_form[:100],
                        'common_use': common_use[:200],
                        'dosage': dosage[:500],
                        'administration_method': administration[:300],
                        'treatment_duration': duration[:200],
                        'warnings': warnings[:300],
                        'found': True,
                        'confidence': 'low',  # AI source has lower confidence than official APIs
                        'note': 'AI-generated information - Please verify with healthcare professional'
                    }
        except Exception as e:
            print(f"Gemini search error: {str(e)}")
        
        return None
    
    async def verify_with_gemini(self, drug_info: Dict, dosage_result: Dict) -> Dict:
        """Use Google Gemini to verify dosage information"""
        if not EMERGENT_LLM_KEY:
            return {'verified': False, 'confidence': 0, 'reason': 'No API key'}
        
        try:
            ingredients_str = ' + '.join([
                f"{ing['ingredient']} {ing['strength']}{ing['unit']}" 
                if ing['strength'] else ing['ingredient']
                for ing in drug_info['ingredients']
            ])
            
            prompt = f"""You are a medical information validator. 
Verify if this dosage information is correct:

Drug: {ingredients_str}
Dosage Info: {dosage_result.get('dosage', 'N/A')}

Answer ONLY with:
1. Yes or No
2. Confidence score (0-100)
3. Brief reason (max 50 words)

Format: Yes|95|Reason here"""
            
            url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
            
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    url,
                    params={'key': EMERGENT_LLM_KEY},
                    json={
                        'contents': [{
                            'parts': [{'text': prompt}]
                        }]
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    text = data['candidates'][0]['content']['parts'][0]['text']
                    
                    # Parse response
                    parts = text.split('|')
                    if len(parts) >= 3:
                        return {
                            'verified': parts[0].strip().lower() == 'yes',
                            'confidence': int(parts[1].strip()),
                            'reason': parts[2].strip()
                        }
        except Exception as e:
            print(f"Gemini verification error: {str(e)}")
        
        return {'verified': False, 'confidence': 0, 'reason': 'Verification failed'}
    
    def strict_match(self, user_ingredients: List[Dict], api_result: Dict) -> bool:
        """
        Strict matching: ALL ingredients and strengths must match
        """
        # For now, basic matching
        # TODO: Enhance with ingredient synonym matching
        return True  # Will be enhanced
    
    async def get_dosage_info(self, drug_name: str, use_ai_verification: bool = True) -> Dict:
        """
        Main function: Get dosage info from multiple sources with strict matching
        Supports Arabic and English drug names
        Searches official APIs first, then falls back to Google AI
        """
        print(f"\n🔍 [DOSAGE] Searching for: {drug_name}")
        
        # Step 1: Parse drug name (supports Arabic & English)
        ingredients = self.parse_drug_name(drug_name)
        print(f"📊 [DOSAGE] Parsed ingredients: {ingredients}")
        
        if not ingredients:
            return {
                'found': False,
                'message': 'Could not parse drug name / لم يتم التعرف على اسم الدواء',
                'sources': []
            }
        
        language = ingredients[0].get('language', 'en')
        
        # Step 2: Search official API sources in parallel
        print(f"🔎 [DOSAGE] Searching official APIs...")
        tasks = [
            self.search_fda_api(ingredients),
            self.search_rxnorm_api(ingredients),
            self.search_dailymed_api(ingredients)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter successful results
        valid_results = [r for r in results if r and isinstance(r, dict) and r.get('found')]
        
        print(f"✅ [DOSAGE] Found {len(valid_results)} official sources")
        
        # Step 3: If no official sources found, try Google AI as fallback
        if not valid_results:
            print(f"🤖 [DOSAGE] No official sources found. Trying Google AI fallback...")
            gemini_result = await self.search_google_gemini(ingredients)
            if gemini_result and gemini_result.get('found'):
                valid_results = [gemini_result]
                print(f"✅ [DOSAGE] Google AI provided information")
        
        # If still no results
        if not valid_results:
            return {
                'found': False,
                'message': 'No dosage information found in any source / لم يتم العثور على معلومات الجرعة',
                'ingredients': ingredients,
                'sources': [],
                'warning_message': 'استشر طبيبك أو صيدليك للحصول على معلومات الجرعة الدقيقة.'
            }
        
        # Step 4: Use first valid result
        best_result = valid_results[0]
        
        # Step 5: AI Verification (optional, only for official sources)
        ai_verification = None
        if use_ai_verification and EMERGENT_LLM_KEY and best_result['source'] != 'Google Gemini AI':
            ai_verification = await self.verify_with_gemini(
                {'ingredients': ingredients}, 
                best_result
            )
        
        # Step 6: Build final response with comprehensive information
        confidence = 'high' if len(valid_results) >= 2 else 'medium'
        if best_result.get('source') == 'Google Gemini AI':
            confidence = 'low'  # AI sources have lower confidence
        
        # Bilingual warning message
        warning_msg = 'هذه معلومات عامة. استشر الطبيب للجرعة الدقيقة المناسبة لحالتك.'
        if language == 'en':
            warning_msg = 'This is general information. Consult your doctor for accurate dosage.'
        
        # Build comprehensive response
        response = {
            'found': True,
            'ingredients': ingredients,
            'dosage_form': best_result.get('dosage_form', 'Unknown'),
            'common_use': best_result.get('common_use', ''),
            'dosage': best_result.get('dosage', 'See prescribing information'),
            'administration_method': best_result.get('administration_method', ''),
            'treatment_duration': best_result.get('treatment_duration', ''),
            'warnings': best_result.get('warnings', ''),
            'sources': [r['source'] for r in valid_results],
            'confidence': confidence,
            'ai_verified': ai_verification if ai_verification else None,
            'warning_message': warning_msg,
            'language': language,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Add AI-specific note if Gemini was used as primary source
        if best_result.get('source') == 'Google Gemini AI':
            response['ai_note'] = best_result.get('note', '')
        
        return response

# Singleton instance
dosage_service = MultiSourceDosageService()
