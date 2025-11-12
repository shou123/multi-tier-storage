from typing import Optional, List
from collections import deque

# Definition for a binary tree node.
class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right


class Solution:
    def isBalanced(self, root: Optional[TreeNode]) -> bool:
        # call helper; if -1 is returned, it's unbalanced
        return self.dfs_height(root) != -1

    def dfs_height(self, node: Optional[TreeNode]) -> int:
        if node is None:
            return 0

        # recursively get left and right subtree heights
        left_h = self.dfs_height(node.left)
        if left_h == -1:
            return -1  # left subtree unbalanced

        right_h = self.dfs_height(node.right)
        if right_h == -1:
            return -1  # right subtree unbalanced

        # check balance condition
        if abs(left_h - right_h) > 1:
            return -1  # current node unbalanced

        # return current node height
        return max(left_h, right_h) + 1


# -------------------------------
# Helper: build tree from list input
# -------------------------------
def build_tree(values: List[Optional[int]]) -> Optional[TreeNode]:
    if not values or values[0] is None:
        return None

    root = TreeNode(values[0])
    queue = deque([root])
    i = 1

    while queue and i < len(values):
        node = queue.popleft()
        if i < len(values) and values[i] is not None:
            node.left = TreeNode(values[i])
            queue.append(node.left)
        i += 1

        if i < len(values) and values[i] is not None:
            node.right = TreeNode(values[i])
            queue.append(node.right)
        i += 1

    return root


# -------------------------------
# Example input
# -------------------------------
root_list = [3, 9, 20, None, None, 15, 7]
root = build_tree(root_list)

# -------------------------------
# Run the solution
# -------------------------------
sol = Solution()
print(sol.isBalanced(root))  # ✅ Expected output: True
