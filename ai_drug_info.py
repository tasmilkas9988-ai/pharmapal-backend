"""
AI-Powered Drug Information System
Uses OpenAI GPT-4 with Emergent LLM Key for accurate medical information
"""
import os
import logging
import asyncio
from typing import Dict

logger = logging.getLogger(__name__)

try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    EMERGENT_AVAILABLE = True
except ImportError:
    EMERGENT_AVAILABLE = False
    logger.warning("emergentintegrations not available")


class AIDrugInfo:
    """Get drug information using AI (OpenAI GPT-4)"""
    
    def __init__(self):
        if not EMERGENT_AVAILABLE:
            raise ValueError("emergentintegrations library not available")
        
        # Get API key
        self.api_key = os.environ.get('EMERGENT_LLM_KEY', 'sk-emergent-5061c801558Df48116')
        self.provider = "openai"
        self.model = "gpt-4o"
    
    async def get_drug_info_async(self, drug_name: str, scientific_name: str = None, language: str = "ar") -> Dict[str, str]:
        """
        Get comprehensive drug information using AI (Async version)
        
        Args:
            drug_name: Trade/brand name (e.g., "Claritine", "Panadol")
            scientific_name: Scientific/generic name (e.g., "Loratidine", "Paracetamol")
            language: Target language ('ar' or 'en')
        
        Returns:
            Dictionary with drug information
        """
        try:
            # Prepare search term (use both names for accuracy)
            search_term = f"{drug_name}"
            if scientific_name and scientific_name != drug_name:
                search_term += f" ({scientific_name})"
            
            # Extract strength/concentration from drug name (e.g., "10MG", "500mg")
            import re
            strength_match = re.search(r'(\d+\.?\d*)\s*(mg|mcg|g|ml|%|ملغ|مجم|جم)', drug_name, re.IGNORECASE)
            strength_info = ""
            if strength_match:
                strength_value = strength_match.group(1)
                strength_unit = strength_match.group(2)
                strength_info = f"\n\n🎯 **مهم جداً**: هذا الدواء بتركيز {strength_value}{strength_unit}. يجب أن تطابق الجرعة الموصى بها هذا التركيز بالضبط!"
            
            # Create prompt for AI
            if language == "ar":
                prompt = f"""أنت صيدلي خبير. أعطني معلومات دقيقة وموثوقة عن الدواء: {search_term}{strength_info}

يجب أن تكون المعلومات:
- دقيقة علمياً
- مختصرة ومفيدة
- بدون مبالغة

أعطني المعلومات التالية بالضبط:

1. التصنيف الدوائي:
(مثال: مضاد للحساسية، مسكن للألم، إلخ - سطر واحد فقط)

2. الاستخدامات:
(أهم 3-4 استخدامات طبية فقط - نقاط مختصرة)

3. الجرعة الموصى بها:
⚠️ **قواعد مهمة للجرعة:**
- إذا كان الدواء بتركيز محدد (مثلاً 10 مجم)، اذكر الجرعة لهذا التركيز فقط
- لا تذكر "الكبار" أو "الأطفال" أو "تتراوح بين"
- فقط اذكر: عدد المرات في اليوم ومدة العلاج
- للكريمات/المراهم: اذكر عدد مرات الاستخدام في اليوم والمدة (مثال: "5 مرات يومياً لمدة 4 أيام")
- مثال صحيح: "10 مجم مرة واحدة يومياً لمدة أسبوعين"
- مثال خاطئ: "الكبار: تتراوح بين 5-40 مجم..."
- **يجب أن تذكر الجرعة دائماً - لا تقل "غير متوفر" إلا إذا كنت متأكداً 100%**

4. محاذير الاستخدام:
(أهم 4-5 محاذير - نقاط مختصرة)

5. الحمل والرضاعة:
(معلومة واحدة مختصرة وواضحة)

⚠️ مهم جداً:
- إذا لم تكن متأكداً من معلومة، اذكر "غير متوفر"
- لا تخترع معلومات
- اعتمد على معلومات طبية موثوقة فقط
- للجرعة: طابق التركيز المذكور بالضبط"""
            else:
                # English version with same strength matching logic
                strength_info_en = ""
                if strength_match:
                    strength_value = strength_match.group(1)
                    strength_unit = strength_match.group(2)
                    strength_info_en = f"\n\n🎯 **IMPORTANT**: This drug has a concentration of {strength_value}{strength_unit}. The recommended dosage MUST match this exact concentration!"
                
                prompt = f"""You are an expert pharmacist. Provide accurate and reliable information about the drug: {search_term}{strength_info_en}

The information must be:
- Scientifically accurate
- Concise and useful
- No exaggeration

Provide the following information exactly:

1. Drug Classification:
(Example: antihistamine, analgesic, etc - one line only)

2. Uses:
(Top 3-4 medical uses only - brief bullet points)

3. Recommended Dosage:
⚠️ **Important Rules for Dosage:**
- If the drug has a specific concentration (e.g., 10mg), state the dosage for THAT concentration only
- Don't mention "adults" or "children" or "ranges between"
- Only state: frequency per day and duration
- For creams/ointments: state number of applications per day and duration (example: "Apply 5 times daily for 4 days")
- Correct example: "10mg once daily for two weeks"
- Wrong example: "Adults: ranges between 5-40mg..."
- **You MUST provide dosage - only say "Not available" if you're 100% certain**

4. Warnings & Precautions:
(Top 4-5 warnings - brief bullet points)

5. Pregnancy & Lactation:
(One brief and clear statement)

⚠️ Very Important:
- If you're not sure about information, say "Not available"
- Don't make up information
- Rely on trusted medical information only
- For dosage: Match the exact concentration mentioned"""
            
            # Create chat instance
            chat = LlmChat(
                api_key=self.api_key,
                session_id=f"drug_info_{drug_name}",
                system_message="You are a professional pharmacist providing accurate, evidence-based drug information. Always prioritize patient safety and accuracy over completeness."
            ).with_model(self.provider, self.model)
            
            # Send message (emergentintegrations async method)
            user_message = UserMessage(text=prompt)
            
            # Call async method directly (we're already in async context)
            content = await chat.send_message(user_message)
            
            # Parse the response
            result = self._parse_ai_response(content, language)
            result["success"] = True
            result["source"] = "AI (OpenAI GPT-4)"
            result["search_term"] = search_term
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting AI drug info: {e}")
            return {
                "success": False,
                "error": str(e),
                "source": "AI"
            }
    
    def get_drug_info(self, drug_name: str, scientific_name: str = None, language: str = "ar") -> Dict[str, str]:
        """
        Get comprehensive drug information using AI (Sync wrapper for backward compatibility)
        
        Args:
            drug_name: Trade/brand name (e.g., "Claritine", "Panadol")
            scientific_name: Scientific/generic name (e.g., "Loratidine", "Paracetamol")
            language: Target language ('ar' or 'en')
        
        Returns:
            Dictionary with drug information
        """
        try:
            # Run async method
            import nest_asyncio
            nest_asyncio.apply()
            
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(
                self.get_drug_info_async(drug_name, scientific_name, language)
            )
            
        except Exception as e:
            logger.error(f"Error getting AI drug info: {e}")
            return {
                "success": False,
                "error": str(e),
                "source": "AI"
            }
    
    def _parse_ai_response(self, content: str, language: str) -> Dict[str, str]:
        """Parse AI response into structured data"""
        try:
            sections = {
                "classification": "",
                "uses": "",
                "dosage": "",
                "warnings": "",
                "pregnancy_lactation": ""
            }
            
            # Split by numbered sections
            lines = content.split('\n')
            current_section = None
            current_content = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Detect section headers
                if language == "ar":
                    # Check if line is a section header (must contain keyword AND colon, OR start with number+dot)
                    is_section_1 = ("التصنيف" in line and ":" in line) or (line.startswith("1.") and "التصنيف" in line)
                    is_section_2 = ("الاستخدامات" in line and ":" in line) or (line.startswith("2.") and "الاستخدامات" in line)
                    is_section_3 = ("الجرعة" in line and ":" in line) or (line.startswith("3.") and "الجرعة" in line)
                    is_section_4 = ("محاذير" in line and ":" in line) or (line.startswith("4.") and "محاذير" in line)
                    is_section_5 = (("الحمل" in line or "الرضاعة" in line) and ":" in line) or (line.startswith("5.") and ("الحمل" in line or "الرضاعة" in line))
                    
                    if is_section_1:
                        if current_section and current_content:
                            sections[current_section] = '\n'.join(current_content).strip()
                        current_section = "classification"
                        current_content = []
                        # Add content after the header if exists
                        if ":" in line:
                            after_colon = line.split(":", 1)[1].strip()
                            if after_colon:
                                current_content.append(after_colon)
                    elif is_section_2:
                        if current_section and current_content:
                            sections[current_section] = '\n'.join(current_content).strip()
                        current_section = "uses"
                        current_content = []
                    elif is_section_3:
                        if current_section and current_content:
                            sections[current_section] = '\n'.join(current_content).strip()
                        current_section = "dosage"
                        current_content = []
                    elif is_section_4:
                        if current_section and current_content:
                            sections[current_section] = '\n'.join(current_content).strip()
                        current_section = "warnings"
                        current_content = []
                    elif is_section_5:
                        if current_section and current_content:
                            sections[current_section] = '\n'.join(current_content).strip()
                        current_section = "pregnancy_lactation"
                        current_content = []
                    else:
                        if current_section:
                            current_content.append(line)
                else:
                    # English section detection - more strict
                    is_section_1_en = ("classification" in line.lower() and ":" in line) or (line.startswith("1.") and "classification" in line.lower())
                    is_section_2_en = ("uses" in line.lower() and ":" in line) or (line.startswith("2.") and "uses" in line.lower())
                    is_section_3_en = ("dosage" in line.lower() and ":" in line) or (line.startswith("3.") and "dosage" in line.lower())
                    is_section_4_en = ("warning" in line.lower() and ":" in line) or (line.startswith("4.") and "warning" in line.lower())
                    is_section_5_en = (("pregnancy" in line.lower() or "lactation" in line.lower()) and ":" in line) or (line.startswith("5.") and ("pregnancy" in line.lower() or "lactation" in line.lower()))
                    
                    if is_section_1_en:
                        if current_section and current_content:
                            sections[current_section] = '\n'.join(current_content).strip()
                        current_section = "classification"
                        current_content = []
                        if ":" in line:
                            after_colon = line.split(":", 1)[1].strip()
                            if after_colon:
                                current_content.append(after_colon)
                    elif is_section_2_en:
                        if current_section and current_content:
                            sections[current_section] = '\n'.join(current_content).strip()
                        current_section = "uses"
                        current_content = []
                    elif is_section_3_en:
                        if current_section and current_content:
                            sections[current_section] = '\n'.join(current_content).strip()
                        current_section = "dosage"
                        current_content = []
                    elif is_section_4_en:
                        if current_section and current_content:
                            sections[current_section] = '\n'.join(current_content).strip()
                        current_section = "warnings"
                        current_content = []
                    elif is_section_5_en:
                        if current_section and current_content:
                            sections[current_section] = '\n'.join(current_content).strip()
                        current_section = "pregnancy_lactation"
                        current_content = []
                    else:
                        if current_section:
                            current_content.append(line)
            
            # Add last section
            if current_section and current_content:
                sections[current_section] = '\n'.join(current_content).strip()
            
            return sections
            
        except Exception as e:
            logger.error(f"Error parsing AI response: {e}")
            # Return raw content as fallback
            return {
                "classification": "",
                "uses": content[:500],
                "dosage": "",
                "warnings": "",
                "pregnancy_lactation": ""
            }


# Test
if __name__ == "__main__":
    print("Testing AI Drug Info System...\n")
    
    try:
        ai = AIDrugInfo()
        
        # Test 1: Claritine (trade name) with Loratidine (scientific)
        print("=" * 60)
        print("Test 1: Claritine (Loratidine)")
        print("=" * 60)
        result = ai.get_drug_info("Claritine", "Loratidine", "ar")
        
        if result['success']:
            print("✅ SUCCESS!")
            print(f"\n🏷️ التصنيف:\n{result.get('classification', 'N/A')}")
            print(f"\n💊 الاستخدامات:\n{result.get('uses', 'N/A')[:200]}")
            print(f"\n⚕️ الجرعة:\n{result.get('dosage', 'N/A')[:150]}")
        else:
            print(f"❌ Failed: {result.get('error')}")
        
        # Test 2: Panadol
        print("\n\n" + "=" * 60)
        print("Test 2: Panadol (Paracetamol)")
        print("=" * 60)
        result2 = ai.get_drug_info("Panadol", "Paracetamol", "ar")
        
        if result2['success']:
            print("✅ SUCCESS!")
            print(f"\n🏷️ التصنيف:\n{result2.get('classification', 'N/A')}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
