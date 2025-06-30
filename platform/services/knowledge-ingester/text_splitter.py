import tiktoken
import re
from typing import List, Optional
from markdown import Markdown
from lxml.html import fromstring as html_fromstring

# --- Configuration for Text Splitting ---
# Using a model like gpt-3.5-turbo for token counting is common
TIKTOKEN_ENCODING_MODEL = "cl100k_base" # Encoding used by gpt-3.5-turbo, gpt-4
DEFAULT_CHUNK_SIZE_TOKENS = 512  # Max number of tokens per chunk
DEFAULT_CHUNK_OVERLAP_TOKENS = 50   # Number of tokens to overlap between chunks

# Initialize tokenizer globally for efficiency
try:
    tokenizer = tiktoken.get_encoding(TIKTOKEN_ENCODING_MODEL)
except Exception:
    tokenizer = tiktoken.encoding_for_model("gpt-3.5-turbo") # Fallback


def count_tokens(text: str) -> int:
    """Counts the number of tokens in a text string."""
    return len(tokenizer.encode(text))

def markdown_to_text(md_content: str) -> str:
    """Converts Markdown to plain text, preserving structure somewhat."""
    # A more sophisticated approach might handle specific elements better
    # (e.g. tables, code blocks) but this is a good start.

    # Convert Markdown to HTML
    md_converter = Markdown(output_format="html")
    html_content = md_converter.convert(md_content)

    # Convert HTML to text using lxml for better structure handling
    # This helps remove HTML tags while trying to maintain readability
    doc = html_fromstring(html_content)
    text_content = doc.text_content() # Extracts all text, attempts to keep line breaks

    # Basic cleaning: remove excessive newlines and leading/trailing whitespace
    text_content = re.sub(r'\n\s*\n', '\n\n', text_content) # Consolidate multiple newlines
    text_content = text_content.strip()
    return text_content


class RecursiveCharacterTextSplitter:
    """
    A simple recursive character text splitter.
    Splits text based on a list of separators, trying larger separators first.
    Aims to keep paragraphs and sentences together.
    """
    def __init__(self, separators: Optional[List[str]] = None, chunk_size: int = DEFAULT_CHUNK_SIZE_TOKENS, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP_TOKENS):
        self._separators = separators or ["\n\n", "\n", ". ", " ", ""] # Default separators
        self._chunk_size = chunk_size # Target chunk size in tokens
        self._chunk_overlap = chunk_overlap # Overlap in tokens

    def split_text(self, text: str) -> List[str]:
        final_chunks = []
        # Attempt to split by the first separator
        separator = self._separators[0]
        try:
            splits = re.split(f"({separator})", text) # Keep separators for rejoining
        except re.error: # Handle cases where separator might be problematic for regex
            splits = text.split(separator)


        # Process splits, re-adding separators where appropriate if re.split with capture was used
        # Simplified: if re.split was not used or capture failed, separators are gone
        # For simplicity, we'll assume split() if re.split fails or is not capturing
        if not any(s == separator for s in splits) and separator != "": # If separator is gone, it means simple split
             processed_splits = []
             for i, part in enumerate(splits):
                 processed_splits.append(part)
                 if i < len(splits) -1 : # Add separator back if it's not the last part
                     processed_splits.append(separator)
             splits = processed_splits

        current_chunk_parts = []
        current_token_count = 0

        for part in splits:
            part_token_count = count_tokens(part)

            if current_token_count + part_token_count > self._chunk_size and current_chunk_parts:
                # Current chunk is full or adding this part would make it too full
                # Finalize current_chunk_parts
                chunk_text = "".join(current_chunk_parts).strip()
                if count_tokens(chunk_text) > self._chunk_size and len(self._separators) > 1:
                    # If it's still too big, recurse with smaller separators
                    final_chunks.extend(RecursiveCharacterTextSplitter(
                        self._separators[1:], self._chunk_size, self._chunk_overlap
                    ).split_text(chunk_text))
                elif chunk_text:
                    final_chunks.append(chunk_text)

                # Start new chunk with overlap
                current_chunk_parts = []
                current_token_count = 0

                # Add overlap from the end of the previous chunk
                # This is a simplified overlap logic. More robust overlap would re-construct
                # the end of the previous chunk and take last N tokens.
                if final_chunks and self._chunk_overlap > 0:
                    # A simple way: take the last part of the previous chunk if it's small enough
                    # This needs to be more sophisticated for token-based overlap.
                    # For now, we'll just restart the chunk and the part that made it overflow
                    # will be the start of the new chunk.
                    # A more robust overlap would involve looking at the previous finalized chunk.
                    pass # Simplified: overlap is implicitly handled by how splits are processed

            current_chunk_parts.append(part)
            current_token_count += part_token_count

        # Add the last remaining chunk
        if current_chunk_parts:
            chunk_text = "".join(current_chunk_parts).strip()
            if count_tokens(chunk_text) > self._chunk_size and len(self._separators) > 1:
                 final_chunks.extend(RecursiveCharacterTextSplitter(
                        self._separators[1:], self._chunk_size, self._chunk_overlap
                    ).split_text(chunk_text))
            elif chunk_text:
                final_chunks.append(chunk_text)

        # Post-process to ensure overlap and handle chunks that are too small
        # This is a basic implementation; libraries like LangChain have more sophisticated splitters.
        # The current overlap logic is very basic. A better approach for overlap:
        # After splitting, if chunk N and N+1 exist, ensure N+1 starts with the last M tokens of N.

        # A more robust token-based overlap strategy:
        # 1. Create initial chunks.
        # 2. Iterate through chunks. For each chunk `C_i`, if `C_{i-1}` exists,
        #    prepend the last `_chunk_overlap` tokens of `C_{i-1}` to `C_i`.
        # This requires decoding/re-encoding tokens which can be slow.
        # The LangChain approach is generally preferred for production use.

        # For this phase, the above recursive split by separators is a starting point.
        # We can refine overlap and final chunk size management later if needed.
        # Let's filter out very small chunks that might result from splitting.
        return [ch for ch in final_chunks if count_tokens(ch) > 10] # Min token size for a chunk


# Example usage:
if __name__ == "__main__":
    sample_markdown = """
# Title

This is the first paragraph. It has some sentences.
This is still the first paragraph.

This is the second paragraph. It's shorter.

### Sub-heading
And a final line of text here. With a full stop. Followed by more.
    """
    plain_text = markdown_to_text(sample_markdown)
    print("--- Plain Text ---")
    print(plain_text)
    print("\n--- Tokens in Plain Text ---")
    print(count_tokens(plain_text))

    splitter = RecursiveCharacterTextSplitter(chunk_size=30, chunk_overlap=5)
    chunks = splitter.split_text(plain_text)

    print("\n--- Chunks ---")
    for i, chunk in enumerate(chunks):
        print(f"Chunk {i+1} (Tokens: {count_tokens(chunk)}):\n{chunk}\n")

    long_text = "This is a very long sentence that will definitely need to be split multiple times because its token count will exceed the small chunk size we have set for testing purposes. We are trying to see how the recursive splitter handles this situation and whether it manages to break it down effectively. Another sentence follows. And one more for good measure." * 5
    print(f"\n--- Long Text (Tokens: {count_tokens(long_text)}) ---")
    chunks_long = splitter.split_text(long_text)
    for i, chunk in enumerate(chunks_long):
        print(f"Chunk {i+1} (Tokens: {count_tokens(chunk)}):\n{chunk}\n")

    # Test with only spaces as separator
    splitter_space = RecursiveCharacterTextSplitter(separators=[" "], chunk_size=10, chunk_overlap=2)
    text_no_newline = "Word1 Word2 Word3 Word4 Word5 Word6 Word7 Word8 Word9 Word10 Word11 Word12 Word13 Word14 Word15"
    print(f"\n--- Text No Newline (Tokens: {count_tokens(text_no_newline)}) ---")
    chunks_space = splitter_space.split_text(text_no_newline)
    for i, chunk in enumerate(chunks_space):
        print(f"Chunk {i+1} (Tokens: {count_tokens(chunk)}):\n{chunk}\n")

    # Test with a very long single word (pathological case for simple char splitters)
    # Tokenizer will split this, but character based splitters might struggle without token awareness.
    long_word_text = "Supercalifragilisticexpialidocious" * 10
    print(f"\n--- Long Word Text (Tokens: {count_tokens(long_word_text)}) ---") # Tiktoken handles this
    chunks_long_word = splitter.split_text(long_word_text) # Our splitter will likely make one large chunk or split by " " (empty string)
    for i, chunk in enumerate(chunks_long_word):
        print(f"Chunk {i+1} (Tokens: {count_tokens(chunk)}):\n{chunk}\n")

    # The current splitter is character-based after initial separator split.
    # True token-based splitting (like LangChain's TokenTextSplitter) is more robust
    # as it directly works with token counts for splitting and overlap.
    # This implementation is a simplified version for Phase 4.
    pass
