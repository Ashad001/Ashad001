#include <iostream>
#include <vector>
using namespace std;

vector<int> LinearSearch2D(vector<vector<int> > (arr), int target)
{
    vector<int> out = {-1, -1};
    for (int row = 0; row < arr.size(); row++)
    {
        for (int col = 0; col < arr[row].size(); col++)
        {
            if (arr[row][col] == target)
            {
                out[0] = row;
                out[1] = col;
            }
        }
    }
    return out;
}

int main(int argc, char const *argv[])
{
    vector<vector<int> > in{
        {1,2,3},
        {4,5,6},
        {7,8,9}
    };
    vector<int> ans = LinearSearch2D((in), 6);
    cout << ans[0] << " " << ans[1] << endl;
    return 0;
}
